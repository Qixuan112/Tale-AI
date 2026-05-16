"""
PlanLLM - 日程规划与记事本管理系统

作为当日记事本管理员，负责：
1. 管理每日日程安排（当日记事本）
2. 维护长期目标（长期记事本）
3. 协调时间表，处理时间冲突
4. 自动清理已过期的行程
5. 双向同步：PlanLLM ↔ 当日记事本 ↔ 长期记事本
"""

import os
import json
import uuid
import asyncio
from datetime import datetime, time, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI
from filelock import FileLock

from ..bus import bus
from ..config import provide
from ..config.prompt import PLAN_PROMPT
from ..utils import get_logger
from .diary_models import (
    DiaryEntry, DailyPlan, Goal, LongTermGoals,
    EventType, Priority, EventStatus
)

logger = get_logger(__name__)


class PlanLLM:
    """
    PlanLLM - 当日记事本管理员
    
    职责：
    - 制定每日计划（起床时生成当日日程）
    - 动态添加/修改/删除日程条目
    - 协调时间表，处理时间冲突
    - 清理已过期行程
    - 与长期记事本双向同步
    
    使用示例：
        # 初始化
        planllm = PlanLLM()
        
        # 制定今日计划
        plan = planllm.generate_daily_plan("制定今天的学习计划")
        
        # 添加新行程（来自LLM请求）
        planllm.add_event_from_request("今天下午张三要我去茶园会")
        
        # 获取当前日程
        current_plan = planllm.get_today_plan()
    """
    
    def __init__(self, api_key=None, model=None, url=None, max_context=10):
        """
        初始化 PlanLLM
        
        Args:
            api_key: OpenAI API 密钥
            model: 使用的模型
            url: API 基础 URL
            max_context: 最大上下文消息数
        """
        self.client = OpenAI(
            api_key=api_key or provide.PLAN_API_KEY,
            base_url=url or provide.PLAN_URL,
        )
        self.model = model or provide.PLAN_MODEL
        self.max_context = max_context
        
        # 数据存储路径
        self.data_dir = Path("data/diary")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 当前日期
        self._current_date = datetime.now().date()
        
        # 加载数据
        self._today_plan: Optional[DailyPlan] = None
        self._long_term_goals: LongTermGoals = LongTermGoals()
        
        # 线程池用于异步执行
        self._executor = ThreadPoolExecutor(max_workers=2)
        
        self._load_data()
        
        # 检查是否需要创建新日期的计划
        self._check_new_day()
    
    def _get_plan_file_path(self, date: datetime.date) -> Path:
        """获取某日期程文件路径"""
        return self.data_dir / f"plan_{date.isoformat()}.json"
    
    def _get_goals_file_path(self) -> Path:
        """获取长期目标文件路径"""
        return self.data_dir / "long_term_goals.json"
    
    def _load_data(self):
        """加载数据（带文件锁，防止并发读写冲突）"""
        # 加载今日计划
        today_file = self._get_plan_file_path(self._current_date)
        if today_file.exists():
            try:
                lock = FileLock(str(today_file) + ".lock")
                with lock:
                    with open(today_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self._today_plan = DailyPlan.from_dict(data)
            except Exception as e:
                logger.error("加载今日计划失败: %s", e)
                self._today_plan = None

        # 加载长期目标
        goals_file = self._get_goals_file_path()
        if goals_file.exists():
            try:
                lock = FileLock(str(goals_file) + ".lock")
                with lock:
                    with open(goals_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self._long_term_goals = LongTermGoals.from_dict(data)
            except Exception as e:
                logger.error("加载长期目标失败: %s", e)
                self._long_term_goals = LongTermGoals()

    def _save_today_plan(self):
        """保存今日计划（带文件锁）"""
        if self._today_plan:
            try:
                file_path = self._get_plan_file_path(self._today_plan.date)
                lock = FileLock(str(file_path) + ".lock")
                with lock:
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(self._today_plan.to_dict(), f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error("保存今日计划失败: %s", e)

    def _save_long_term_goals(self):
        """保存长期目标（带文件锁）"""
        try:
            file_path = self._get_goals_file_path()
            lock = FileLock(str(file_path) + ".lock")
            with lock:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(self._long_term_goals.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("保存长期目标失败: %s", e)

    def _check_new_day(self):
        """检查是否新的一天，如果是则清理过期行程"""
        today = datetime.now().date()
        if today != self._current_date:
            logger.info("新的一天: %s", today)
            self._current_date = today

            # 保存昨日计划
            if self._today_plan:
                self._save_today_plan()

            # 加载或创建今日计划
            self._load_data()
            if self._today_plan is None:
                self._today_plan = DailyPlan(date=today)

            # 新的一天且无计划 → 标记需要自动生成
            if not self._today_plan.entries and self._today_plan.date == today:
                logger.info("今日无计划，尝试自动生成...")
                try:
                    self.generate_daily_plan("为我制定今天完整的作息计划")
                    logger.info("今日计划已自动生成")
                except Exception as e:
                    logger.error("自动生成今日计划失败: %s", e)
    
    def ensure_today_plan(self):
        """确保今日有计划：如果今日尚无日程，自动生成默认计划

        可在系统启动或 WebUI 加载时调用，确保每天都有计划可用。
        """
        self._check_new_day()

        today = datetime.now().date()
        if not self._today_plan or not self._today_plan.entries:
            logger.info("今日(%s)无计划，自动生成默认计划...", today)
            try:
                self.generate_daily_plan("为我制定今天完整的作息计划")
                logger.info("今日计划已自动生成")
                return True
            except Exception as e:
                logger.error("自动生成今日计划失败: %s", e)
                return False
        return True

    def generate(self, prompt: str) -> str:
        """
        处理计划请求（同步版本，兼容旧接口）
        
        根据 prompt 内容判断是：
        1. 制定每日计划
        2. 添加特定行程
        3. 查询当前日程
        
        Args:
            prompt: 用户请求
            
        Returns:
            处理结果文本
        """
        self._check_new_day()
        
        # 判断请求类型（多层规则分类，优先级从高到低）
        prompt_lower = prompt.lower()

        # 1. 查询请求（最高优先级，显式查询意图）
        query_indicators = [
            "查看", "查询", "看看", "显示", "展示", "列出",
            "有什么安排", "日程是什么", "计划是什么", "安排是什么",
            "今天怎么样", "今天如何", "今天有什么", "今天忙什么",
            "现在几点", "当前日程", "目前安排",
        ]
        if any(kw in prompt_lower for kw in query_indicators):
            return self.get_today_plan_display()

        # 2. 制定计划请求（显式生成/规划意图）
        generation_indicators = [
            "制定", "生成", "规划", "安排一下", "做一份", "写一份",
            "帮我规划", "帮我制定", "给我生成", "创建",
        ]
        if any(kw in prompt_lower for kw in generation_indicators):
            return self.generate_daily_plan(prompt)

        # 3. 添加行程请求（时间模式 + 动作词组合）
        time_patterns = ["下午", "上午", "晚上", "点", "明天", "后天", "周末"]
        action_patterns = ["约", "见", "去", "来", "到", "参加", "开会", "吃饭", "聚餐", "面试", "约会"]
        has_time = any(kw in prompt_lower for kw in time_patterns)
        has_action = any(kw in prompt_lower for kw in action_patterns)
        if has_time and has_action:
            return self.add_event_from_request(prompt)

        # 4. 兜底：若包含时间词但无显式规划意图，偏向添加行程
        if has_time:
            return self.add_event_from_request(prompt)

        # 5. 最终兜底：若包含日程/计划/安排等名词且无显式生成意图，偏向查询
        vague_nouns = ["日程", "计划", "安排"]
        if any(kw in prompt_lower for kw in vague_nouns):
            return self.get_today_plan_display()

        # 6. 默认 fallback：制定计划
        return self.generate_daily_plan(prompt)
    
    async def generate_async(self, prompt: str) -> str:
        """
        异步处理计划请求
        
        将同步的 generate 方法放在线程池中异步执行，
        避免阻塞主事件循环。
        
        Args:
            prompt: 用户请求
            
        Returns:
            处理结果文本
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self.generate, prompt)
    
    def generate_daily_plan(self, prompt: str) -> str:
        """
        制定每日计划
        
        使用 LLM 生成一天的完整日程安排
        
        Args:
            prompt: 计划制定请求
            
        Returns:
            生成的计划文本
        """
        self._check_new_day()
        
        # 构建上下文
        context = self._build_plan_context()
        
        full_prompt = f"""
{context}

用户请求：{prompt}

请为今天制定一个完整的日程计划，包含具体的时间段和活动内容。
请使用 XML 格式输出。
"""
        
        # 调用 LLM
        response = self._call_llm(full_prompt)
        
        # 解析并保存日程
        self._parse_and_save_plan(response)
        
        return response
    
    def add_event_from_request(self, request: str) -> str:
        """
        从自然语言请求中添加行程
        
        例如：
        - "今天下午张三要我去茶园会"
        - "明天上午10点开会"
        - "晚上7点约李四吃饭"
        
        Args:
            request: 自然语言请求
            
        Returns:
            处理结果
        """
        self._check_new_day()
        
        # 使用 LLM 解析请求
        parse_prompt = f"""
请解析以下日程请求，提取关键信息：

请求：{request}

当前时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}

请以 JSON 格式输出：
{{
    "title": "事件标题",
    "description": "事件描述",
    "event_type": "事件类型 (wake/meal/work/study/social/entertainment/rest/exercise/appointment/task/sleep/other)",
    "priority": "优先级 (high/medium/low)",
    "start_time": "开始时间 (HH:MM格式)",
    "end_time": "结束时间 (HH:MM格式，可选)",
    "related_people": ["相关人物"],
    "location": "地点"
}}

注意：
1. 如果请求中没有明确时间，请根据上下文推断合理时间
2. 如果请求中没有明确结束时间，根据事件类型推断合理时长
3. 确保时间是24小时制 HH:MM 格式
"""
        
        try:
            response = self._call_llm(parse_prompt)
            
            # 提取 JSON
            json_str = self._extract_json(response)
            event_data = json.loads(json_str)
            
            # 创建日程条目
            entry = DiaryEntry(
                id=str(uuid.uuid4())[:8],
                title=event_data.get("title", "未命名事件"),
                description=event_data.get("description", ""),
                event_type=EventType(event_data.get("event_type", "other")),
                priority=Priority(event_data.get("priority", "medium")),
                start_time=datetime.strptime(event_data["start_time"], "%H:%M").time(),
                end_time=datetime.strptime(event_data["end_time"], "%H:%M").time() if event_data.get("end_time") else None,
                related_people=event_data.get("related_people", []),
                location=event_data.get("location"),
                source="user"
            )
            
            # 添加到今日计划
            if self._today_plan is None:
                self._today_plan = DailyPlan(date=self._current_date)
            
            # 检查时间冲突
            if self._today_plan._check_conflict(entry):
                # 尝试找到可用时间段
                available_slot = self._today_plan.find_slot(
                    duration_minutes=60 if not entry.end_time else 
                    int((datetime.combine(datetime.today(), entry.end_time) - 
                         datetime.combine(datetime.today(), entry.start_time)).total_seconds() / 60),
                    after_time=entry.start_time
                )
                
                if available_slot:
                    old_time = entry.start_time
                    entry.start_time = available_slot
                    if entry.end_time:
                        duration = (datetime.combine(datetime.today(), entry.end_time) - 
                                   datetime.combine(datetime.today(), old_time)).total_seconds()
                        entry.end_time = (datetime.combine(datetime.today(), available_slot) + 
                                         timedelta(seconds=duration)).time()
                    
                    success = self._today_plan.add_entry(entry)
                    if success:
                        self._save_today_plan()
                        return f"✅ 已添加行程：{entry.title}\n时间调整为 {entry.start_time.strftime('%H:%M')}（原时间冲突）"
                
                return f"❌ 无法添加行程：{entry.title}\n原因：与现有日程冲突，且无法找到可用时间段"
            
            success = self._today_plan.add_entry(entry)
            if success:
                self._save_today_plan()
                time_str = f"{entry.start_time.strftime('%H:%M')}"
                if entry.end_time:
                    time_str += f"-{entry.end_time.strftime('%H:%M')}"
                return f"✅ 已添加行程：{entry.title}\n时间：{time_str}"
            else:
                return f"❌ 添加失败：{entry.title}"
                
        except Exception as e:
            logger.error("添加行程失败: %s", e)
            return f"❌ 添加行程失败: {str(e)}"
    
    def remove_event(self, entry_id: str) -> bool:
        """移除行程"""
        if self._today_plan:
            success = self._today_plan.remove_entry(entry_id)
            if success:
                self._save_today_plan()
            return success
        return False
    
    def update_event(self, entry_id: str, **kwargs) -> bool:
        """更新行程"""
        if self._today_plan:
            success = self._today_plan.update_entry(entry_id, **kwargs)
            if success:
                self._save_today_plan()
            return success
        return False
    
    def get_today_plan(self) -> Optional[DailyPlan]:
        """获取今日计划"""
        self._check_new_day()
        return self._today_plan
    
    def get_today_plan_display(self) -> str:
        """获取今日计划显示文本"""
        self._check_new_day()
        
        # 如果今天还没有计划，返回空状态提示
        if self._today_plan is None or not self._today_plan.entries:
            return "📭 今日暂无日程安排"
        
        # 更新过期条目状态（保留历史记录）
        current_time = datetime.now().time()
        self._today_plan.cleanup_expired(current_time)
        
        # 检查是否还有未过期的条目
        upcoming = self._today_plan.get_upcoming_entries(current_time)
        if not upcoming:
            return "📭 今日日程已全部过期，暂无新的安排"
        
        return self._today_plan.format_display()
    
    def get_upcoming_events(self) -> List[DiaryEntry]:
        """获取即将到来的事件"""
        if self._today_plan:
            current_time = datetime.now().time()
            return self._today_plan.get_upcoming_entries(current_time)
        return []
    
    def add_goal(self, title: str, description: str = "", category: str = "other",
                 priority: str = "medium", target_date: Optional[str] = None) -> Goal:
        """
        添加长期目标
        
        Args:
            title: 目标标题
            description: 目标描述
            category: 分类
            priority: 优先级
            target_date: 目标日期 (YYYY-MM-DD)
            
        Returns:
            创建的 Goal 对象
        """
        goal = Goal(
            id=str(uuid.uuid4())[:8],
            title=title,
            description=description,
            category=category,
            priority=Priority(priority),
            target_date=datetime.strptime(target_date, "%Y-%m-%d").date() if target_date else None
        )
        
        self._long_term_goals.add_goal(goal)
        self._save_long_term_goals()
        
        return goal
    
    def get_goals(self) -> List[Goal]:
        """获取所有长期目标"""
        return self._long_term_goals.goals
    
    def sync_goal_to_diary(self, goal_id: str) -> bool:
        """
        将长期目标同步到今日日程
        
        例如：目标"学会Python"可以分解为"今天学习Python基础语法1小时"
        
        Args:
            goal_id: 目标ID
            
        Returns:
            是否成功同步
        """
        goal = self._long_term_goals.get_goal(goal_id)
        if not goal:
            return False
        
        # 使用 LLM 生成今日任务
        sync_prompt = f"""
请将以下长期目标分解为今天的具体任务：

目标：{goal.title}
描述：{goal.description}
分类：{goal.category}
当前进度：{goal.progress}%

请生成一个适合今天完成的任务，包括：
1. 任务标题
2. 任务描述
3. 建议时间段
4. 预计时长

以 JSON 格式输出：
{{
    "title": "任务标题",
    "description": "任务描述",
    "suggested_time": "建议时间 (HH:MM)",
    "duration_minutes": 预计时长（分钟）
}}
"""
        
        try:
            response = self._call_llm(sync_prompt)
            json_str = self._extract_json(response)
            task_data = json.loads(json_str)
            
            # 创建日程条目
            entry = DiaryEntry(
                id=str(uuid.uuid4())[:8],
                title=task_data["title"],
                description=task_data["description"],
                event_type=EventType.TASK,
                priority=goal.priority,
                start_time=datetime.strptime(task_data["suggested_time"], "%H:%M").time(),
                end_time=(datetime.strptime(task_data["suggested_time"], "%H:%M") + 
                         timedelta(minutes=task_data["duration_minutes"])).time(),
                source="goal"
            )
            
            if self._today_plan is None:
                self._today_plan = DailyPlan(date=self._current_date)
            
            # 检查冲突并调整
            if self._today_plan._check_conflict(entry):
                available_slot = self._today_plan.find_slot(
                    duration_minutes=task_data["duration_minutes"],
                    after_time=entry.start_time
                )
                if available_slot:
                    entry.start_time = available_slot
                    entry.end_time = (datetime.combine(datetime.today(), available_slot) + 
                                     timedelta(minutes=task_data["duration_minutes"])).time()
                else:
                    return False
            
            success = self._today_plan.add_entry(entry)
            if success:
                goal.related_entries.append(entry.id)
                self._save_today_plan()
                self._save_long_term_goals()
            
            return success
            
        except Exception as e:
            logger.error("同步目标失败: %s", e)
            return False
    
    def _call_llm(self, prompt: str) -> str:
        """调用 LLM（使用独立上下文，避免对话历史污染计划生成）"""
        messages = [
            {"role": "system", "content": PLAN_PROMPT},
            {"role": "user", "content": prompt}
        ]
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages
        )
        
        assistant_reply = response.choices[0].message.content
        return assistant_reply
    
    def _trim_context(self):
        """修剪上下文"""
        while len(self.messages) > self.max_context:
            if len(self.messages) >= 3:
                del self.messages[1:3]
    
    def _build_plan_context(self) -> str:
        """构建计划制定的上下文信息"""
        context_parts = []
        
        # 当前时间
        now = datetime.now()
        context_parts.append(f"当前时间：{now.strftime('%Y年%m月%d日 %H:%M')}")
        context_parts.append(f"星期：{['一', '二', '三', '四', '五', '六', '日'][now.weekday()]}")
        
        # 今日已有日程
        if self._today_plan and self._today_plan.entries:
            context_parts.append("\n今日已有日程：")
            for entry in self._today_plan.entries:
                context_parts.append(f"  - {entry}")
        
        # 长期目标
        active_goals = self._long_term_goals.get_active_goals()
        if active_goals:
            context_parts.append("\n进行中的长期目标：")
            for goal in active_goals[:5]:  # 最多显示5个
                context_parts.append(f"  - {goal.title} ({goal.progress}%)")
        
        return "\n".join(context_parts)
    
    def _parse_and_save_plan(self, plan_text: str):
        """解析 JSON 格式的计划文本并保存为 DiaryEntry"""
        if self._today_plan is None:
            self._today_plan = DailyPlan(date=self._current_date)
        
        try:
            # 提取 JSON
            json_str = self._extract_json(plan_text)
            plan_data = json.loads(json_str)
            
            # 解析 entries
            if "plan" in plan_data and "entries" in plan_data["plan"]:
                for entry_data in plan_data["plan"]["entries"]:
                    # 解析时间
                    time_str = entry_data.get("time", "")
                    if "-" in time_str:
                        start_str, end_str = time_str.split("-")
                        start_time = datetime.strptime(start_str.strip(), "%H:%M").time()
                        end_time = datetime.strptime(end_str.strip(), "%H:%M").time()
                    else:
                        start_time = datetime.strptime(time_str.strip(), "%H:%M").time()
                        end_time = None
                    
                    # 创建 DiaryEntry
                    entry = DiaryEntry(
                        id=entry_data.get("id", str(uuid.uuid4())[:8]),
                        title=entry_data.get("title", "未命名"),
                        description=entry_data.get("description", ""),
                        event_type=EventType(entry_data.get("type", "other")),
                        priority=Priority(entry_data.get("priority", "medium")),
                        start_time=start_time,
                        end_time=end_time,
                        source="plan"
                    )
                    
                    # 添加计划条目，检查冲突并自动调整时间
                    if not self._today_plan.add_entry(entry):
                        # 冲突，尝试找可用时间段
                        duration = 60
                        if entry.end_time:
                            duration = int((datetime.combine(datetime.today(), entry.end_time) -
                                          datetime.combine(datetime.today(), entry.start_time)).total_seconds() / 60)
                        
                        available_slot = self._today_plan.find_slot(
                            duration_minutes=duration,
                            after_time=entry.start_time
                        )
                        
                        if available_slot:
                            old_start = entry.start_time
                            entry.start_time = available_slot
                            if entry.end_time:
                                duration_td = datetime.combine(datetime.today(), entry.end_time) - datetime.combine(datetime.today(), old_start)
                                entry.end_time = (datetime.combine(datetime.today(), available_slot) + duration_td).time()
                            
                            if self._today_plan.add_entry(entry):
                                logger.info("计划条目 '%s' 时间已调整为 %s（避免冲突）", entry.title, entry.start_time.strftime("%H:%M"))
                            else:
                                logger.warning("无法添加计划条目 '%s'：即使调整后仍有冲突", entry.title)
                        else:
                            logger.warning("无法添加计划条目 '%s'：时间冲突且找不到可用时间段", entry.title)
                
                # 排序并保存
                self._today_plan._sort_entries()
                
            # 保存 summary
            if "plan" in plan_data and "summary" in plan_data["plan"]:
                self._today_plan.summary = plan_data["plan"]["summary"]
            else:
                self._today_plan.summary = plan_text[:500]
                
            self._save_today_plan()
            logger.info("已保存 %d 个日程条目", len(self._today_plan.entries))

        except Exception as e:
            logger.error("解析计划失败: %s", e)
            # 回退：保存原始文本
            self._today_plan.summary = plan_text[:500]
            self._save_today_plan()
    
    def _extract_json(self, text: str) -> str:
        """从文本中提取 JSON"""
        # 尝试找到 JSON 代码块
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            return text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            return text[start:end].strip()
        else:
            # 尝试找到花括号包裹的内容
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return text[start:end]
        return text
    
    def clear_history(self):
        """清空对话历史（已废弃，PlanLLM 使用无状态调用）"""
        pass
    
    def get_history(self) -> List[Dict]:
        """获取对话历史（已废弃，PlanLLM 使用无状态调用）"""
        return []


# 全局实例（懒加载）
_planllm_instance: Optional[PlanLLM] = None
_planllm_subscribed = False


def get_planllm() -> PlanLLM:
    """工厂函数：懒初始化全局 PlanLLM 实例"""
    global _planllm_instance, _planllm_subscribed
    if _planllm_instance is None:
        _planllm_instance = PlanLLM()
    if not _planllm_subscribed:
        bus.on("plan", lambda prompt: _planllm_instance.generate(prompt))
        _planllm_subscribed = True
    return _planllm_instance


# 便捷函数
def add_event(request: str) -> str:
    """便捷函数：添加行程"""
    return get_planllm().add_event_from_request(request)


def get_today_schedule() -> str:
    """便捷函数：获取今日日程"""
    return get_planllm().get_today_plan_display()


def add_goal(title: str, **kwargs) -> Goal:
    """便捷函数：添加目标"""
    return get_planllm().add_goal(title, **kwargs)
