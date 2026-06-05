"""
日程管理数据模型
定义当日记事本和长期记事本的数据结构
"""

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import Enum
from typing import List, Optional, Dict, Any
import json


class EventType(Enum):
    """事件类型"""
    WAKE = "wake"           # 起床
    MEAL = "meal"           # 用餐
    WORK = "work"           # 工作
    STUDY = "study"         # 学习
    SOCIAL = "social"       # 社交
    ENTERTAINMENT = "entertainment"  # 娱乐
    REST = "rest"           # 休息
    EXERCISE = "exercise"   # 运动
    APPOINTMENT = "appointment"  # 约会/约定
    TASK = "task"           # 任务
    SLEEP = "sleep"         # 睡眠
    OTHER = "other"         # 其他


class Priority(Enum):
    """优先级"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EventStatus(Enum):
    """事件状态"""
    PENDING = "pending"     # 待进行
    ONGOING = "ongoing"     # 进行中
    COMPLETED = "completed" # 已完成
    CANCELLED = "cancelled" # 已取消
    MISSED = "missed"       # 已错过


@dataclass
class DiaryEntry:
    """
    日程条目（单个事件）
    
    例如：下午3点去茶园会见张三
    """
    id: str                                 # 唯一标识
    title: str                              # 事件标题
    description: str                        # 事件描述
    event_type: EventType                   # 事件类型
    priority: Priority                      # 优先级
    
    # 时间信息
    start_time: time                        # 开始时间
    end_time: Optional[time] = None         # 结束时间（可选）
    
    # 状态
    status: EventStatus = EventStatus.PENDING
    
    # 关联信息
    related_people: List[str] = field(default_factory=list)  # 相关人物
    location: Optional[str] = None          # 地点
    source: str = "plan"                    # 来源：plan(计划生成)/user(用户添加)/goal(目标分解)
    
    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
    # 扩展字段
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "event_type": self.event_type.value,
            "priority": self.priority.value,
            "start_time": self.start_time.strftime("%H:%M"),
            "end_time": self.end_time.strftime("%H:%M") if self.end_time else None,
            "status": self.status.value,
            "related_people": self.related_people,
            "location": self.location,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "DiaryEntry":
        """从字典创建"""
        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            event_type=EventType(data["event_type"]),
            priority=Priority(data["priority"]),
            start_time=datetime.strptime(data["start_time"], "%H:%M").time(),
            end_time=datetime.strptime(data["end_time"], "%H:%M").time() if data.get("end_time") else None,
            status=EventStatus(data.get("status", "pending")),
            related_people=data.get("related_people", []),
            location=data.get("location"),
            source=data.get("source", "plan"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            metadata=data.get("metadata", {})
        )
    
    def is_expired(self, current_time: time) -> bool:
        """检查事件是否已过期"""
        if self.end_time:
            return current_time > self.end_time
        else:
            # 如果没有结束时间，假设事件持续1小时
            end = (datetime.combine(datetime.today(), self.start_time) + timedelta(hours=1)).time()
            return current_time > end
    
    def is_upcoming(self, current_time: time, within_minutes: int = 30) -> bool:
        """检查事件是否即将开始"""
        now = datetime.combine(datetime.today(), current_time)
        start = datetime.combine(datetime.today(), self.start_time)
        diff = (start - now).total_seconds() / 60
        return 0 < diff <= within_minutes
    
    def __str__(self) -> str:
        time_str = f"{self.start_time.strftime('%H:%M')}"
        if self.end_time:
            time_str += f"-{self.end_time.strftime('%H:%M')}"
        return f"[{time_str}] {self.title} ({self.status.value})"


@dataclass
class DailyPlan:
    """
    每日计划（当日记事本）
    
    包含一天的所有日程安排
    """
    date: datetime.date                     # 日期
    entries: List[DiaryEntry] = field(default_factory=list)  # 日程条目
    summary: str = ""                       # 每日总结
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def add_entry(self, entry: DiaryEntry) -> bool:
        """
        添加日程条目，自动处理时间冲突
        
        Returns:
            bool: 是否成功添加
        """
        # 检查时间冲突
        if self._check_conflict(entry):
            return False
        
        self.entries.append(entry)
        self._sort_entries()
        self.updated_at = datetime.now()
        return True
    
    def remove_entry(self, entry_id: str) -> bool:
        """移除日程条目"""
        for i, entry in enumerate(self.entries):
            if entry.id == entry_id:
                del self.entries[i]
                self.updated_at = datetime.now()
                return True
        return False
    
    def update_entry(self, entry_id: str, **kwargs) -> bool:
        """更新日程条目"""
        for entry in self.entries:
            if entry.id == entry_id:
                for key, value in kwargs.items():
                    if hasattr(entry, key):
                        setattr(entry, key, value)
                entry.updated_at = datetime.now()
                self.updated_at = datetime.now()
                return True
        return False
    
    def _check_conflict(self, new_entry: DiaryEntry) -> bool:
        """检查时间冲突"""
        new_start = datetime.combine(self.date, new_entry.start_time)
        new_end = datetime.combine(self.date, new_entry.end_time) if new_entry.end_time else new_start + timedelta(hours=1)

        for entry in self.entries:
            if entry.id == new_entry.id:
                continue

            exist_start = datetime.combine(self.date, entry.start_time)
            exist_end = datetime.combine(self.date, entry.end_time) if entry.end_time else exist_start + timedelta(hours=1)
            
            # 检查是否有重叠
            if (new_start < exist_end) and (new_end > exist_start):
                return True
        
        return False
    
    def _sort_entries(self):
        """按时间排序条目"""
        self.entries.sort(key=lambda e: e.start_time)
    
    def get_upcoming_entries(self, current_time: time) -> List[DiaryEntry]:
        """获取即将到来的条目（未过期）"""
        return [e for e in self.entries if not e.is_expired(current_time)]
    
    def get_expired_entries(self, current_time: time) -> List[DiaryEntry]:
        """获取已过期条目"""
        return [e for e in self.entries if e.is_expired(current_time)]
    
    def cleanup_expired(self, current_time: time) -> List[DiaryEntry]:
        """
        标记已过期条目状态，保留历史记录
        
        Returns:
            已过期的条目列表
        """
        expired = self.get_expired_entries(current_time)
        for entry in expired:
            if entry.status == EventStatus.PENDING:
                entry.status = EventStatus.MISSED
            # 保留历史记录，不再从列表中移除
        self.updated_at = datetime.now()
        return expired
    
    def find_slot(self, duration_minutes: int = 60, after_time: Optional[time] = None) -> Optional[time]:
        """
        查找可用时间段
        
        Args:
            duration_minutes: 需要的时长（分钟）
            after_time: 在此时间之后查找
            
        Returns:
            可用开始时间，如果没有则返回 None
        """
        if after_time is None:
            after_time = datetime.now().time()
        
        # 从 after_time 开始，每30分钟检查一次
        current = datetime.combine(datetime.today(), after_time)
        end_of_day = datetime.combine(datetime.today(), time(23, 59))
        iterations = 0

        while current + timedelta(minutes=duration_minutes) <= end_of_day:
            slot_start = current.time()
            slot_end = (current + timedelta(minutes=duration_minutes)).time()
            iterations += 1
            if iterations > 48:
                break

            # 检查是否与现有条目冲突
            conflict = False
            for entry in self.entries:
                entry_start = datetime.combine(datetime.today(), entry.start_time)
                entry_end = datetime.combine(datetime.today(), entry.end_time) if entry.end_time else entry_start + timedelta(hours=1)
                
                slot_start_dt = datetime.combine(datetime.today(), slot_start)
                slot_end_dt = datetime.combine(datetime.today(), slot_end)
                
                if (slot_start_dt < entry_end) and (slot_end_dt > entry_start):
                    conflict = True
                    current = entry_end  # 跳到冲突条目结束后
                    break
            
            if not conflict:
                return slot_start
        
        return None
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "date": self.date.isoformat(),
            "entries": [e.to_dict() for e in self.entries],
            "summary": self.summary,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "DailyPlan":
        """从字典创建"""
        return cls(
            date=datetime.fromisoformat(data["date"]).date() if data.get("date") else datetime.now().date(),
            entries=[DiaryEntry.from_dict(e) for e in data.get("entries", [])],
            summary=data.get("summary", ""),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now()
        )
    
    def format_display(self) -> str:
        """格式化显示"""
        lines = [f"📅 {self.date.strftime('%Y年%m月%d日')} 日程安排", "=" * 40]
        
        if not self.entries:
            lines.append("暂无安排")
        else:
            for entry in self.entries:
                status_icon = {
                    EventStatus.PENDING: "⏳",
                    EventStatus.ONGOING: "▶️",
                    EventStatus.COMPLETED: "✅",
                    EventStatus.CANCELLED: "❌",
                    EventStatus.MISSED: "⏰"
                }.get(entry.status, "⏳")
                
                lines.append(f"{status_icon} {entry}")
        
        if self.summary:
            lines.extend(["", f"📝 总结: {self.summary}"])
        
        return "\n".join(lines)


@dataclass
class Goal:
    """
    长期目标/记事本条目
    
    例如：学会Python、读完某本书、完成某个项目
    """
    id: str                                 # 唯一标识
    title: str                              # 目标标题
    description: str                        # 目标描述
    category: str                           # 分类（学习/工作/健康/社交等）
    priority: Priority                      # 优先级
    
    # 时间规划
    target_date: Optional[datetime.date] = None  # 目标完成日期
    created_at: datetime = field(default_factory=datetime.now)
    
    # 进度
    progress: int = 0                       # 进度百分比 (0-100)
    status: str = "active"                  # active/paused/completed/abandoned
    
    # 子任务
    subtasks: List[Dict[str, Any]] = field(default_factory=list)
    
    # 关联的日程条目ID
    related_entries: List[str] = field(default_factory=list)
    
    # 反思记录
    reflections: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "priority": self.priority.value,
            "target_date": self.target_date.isoformat() if self.target_date else None,
            "created_at": self.created_at.isoformat(),
            "progress": self.progress,
            "status": self.status,
            "subtasks": self.subtasks,
            "related_entries": self.related_entries,
            "reflections": self.reflections
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Goal":
        """从字典创建"""
        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            category=data.get("category", "other"),
            priority=Priority(data.get("priority", "medium")),
            target_date=datetime.fromisoformat(data.get("target_date")).date() if data.get("target_date") else None,
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            progress=data.get("progress", 0),
            status=data.get("status", "active"),
            subtasks=data.get("subtasks", []),
            related_entries=data.get("related_entries", []),
            reflections=data.get("reflections", [])
        )
    
    def update_progress(self, progress: int):
        """更新进度"""
        self.progress = max(0, min(100, progress))
        if self.progress >= 100:
            self.status = "completed"
    
    def add_reflection(self, content: str):
        """添加反思记录"""
        self.reflections.append({
            "date": datetime.now().isoformat(),
            "content": content
        })


@dataclass
class LongTermGoals:
    """
    长期记事本（目标管理）
    
    管理长期目标、愿望清单、成长计划
    """
    goals: List[Goal] = field(default_factory=list)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def add_goal(self, goal: Goal):
        """添加目标"""
        self.goals.append(goal)
        self.updated_at = datetime.now()
    
    def remove_goal(self, goal_id: str) -> bool:
        """移除目标"""
        for i, goal in enumerate(self.goals):
            if goal.id == goal_id:
                del self.goals[i]
                self.updated_at = datetime.now()
                return True
        return False
    
    def get_goal(self, goal_id: str) -> Optional[Goal]:
        """获取目标"""
        for goal in self.goals:
            if goal.id == goal_id:
                return goal
        return None
    
    def get_active_goals(self) -> List[Goal]:
        """获取进行中的目标"""
        return [g for g in self.goals if g.status == "active"]
    
    def get_goals_by_category(self, category: str) -> List[Goal]:
        """按分类获取目标"""
        return [g for g in self.goals if g.category == category]
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "goals": [g.to_dict() for g in self.goals],
            "updated_at": self.updated_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "LongTermGoals":
        """从字典创建"""
        return cls(
            goals=[Goal.from_dict(g) for g in data.get("goals", [])],
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now()
        )
