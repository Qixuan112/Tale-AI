# PR合并指南

基于代码审查发现的冲突，本文档提供详细的合并步骤。

## 冲突总览

### 🔴 严重冲突（需要手动合并）

1. **PR #151 vs PR #156** - core/main.py:540-578行
2. **PR #154 vs #155 vs #157** - core/config/prompt.py:97-130行
3. **PR #155 vs #159** - 重复删除<tool>

## 阶段1：P0基础层（4-6小时）

### Step 1: 合并PR #151
```bash
git checkout main
git pull origin main
gh pr merge 151 --squash -t "fix: 消息元数据ID脱敏" -b "已修复3个CRITICAL问题"
```

### Step 2: 更新PR #154
PR #154已自动更新文档，可直接合并：
```bash
gh pr merge 154 --squash
```

### Step 3: 手动合并PR #156到#151基础上

**冲突位置**：main.py:540-578行

**解决方案**：
```python
# 在#156的结构化代码中集成#151的脱敏逻辑
masked_sender_id = self._id_sanitizer.sanitize_user_id(sender_id)
masked_group_id = self._id_sanitizer.sanitize_group_id(group_id) if group_id else None

# 使用#156的结构化格式
metadata_lines = [
    "[消息元数据]",
    f"- 消息ID: {message_id}",
    f"- 发送者: {sender_name} ({masked_sender_id})",  # 使用脱敏ID
]
```

**执行**：
```bash
git checkout main
git checkout -b merge-151-154-156
# 手动编辑main.py整合两个PR的逻辑
git add core/main.py
git commit -m "merge: 整合#151脱敏 + #156结构化"
git push origin merge-151-154-156
gh pr create --base main
```

### Step 4: 调整PR #153注入方式

PR #153依赖#156的结构化，需要调整：
```python
# 原#153代码（字符串追加）
# user_input += f"\n\n[今日日程]\n{today_plan}"

# 改为在#156结构化中添加
sections.append(f"\n## 你的今日日程\n{today_plan}")
```

## 阶段2：P1 Prompt层（3-4小时）

### Step 5: 合并PR #155
```bash
git checkout main
git pull origin main
gh pr merge 155 --squash
```

### Step 6: 合并PR #158
```bash
gh pr merge 158 --squash
```

### Step 7: Rebase PR #157
```bash
git checkout <PR #157 branch>
git rebase main
# 解决冲突（基于#155精简后的结构）
git push origin HEAD --force
gh pr merge 157 --squash
```

## 阶段3：P2清理层（1-2小时）

### Step 8: 合并PR #159
```bash
# 已修复残留引用
gh pr merge 159 --squash
```

## 测试清单

每个阶段完成后必须测试：

### 阶段1测试
- [ ] ID脱敏生效
- [ ] @用户和引用功能正常
- [ ] session_send支持打码ID
- [ ] 结构化user_input正确传递
- [ ] today_plan正确注入

### 阶段2测试
- [ ] Prompt长度从574→~300行
- [ ] AI回复质量未下降
- [ ] Few-shot示例格式统一

### 阶段3测试
- [ ] <tool>标签完全移除
- [ ] 工具调用通过<act>正常工作

## 预计时间线

- 第1天：阶段1（P0基础层）
- 第2天：阶段2（P1 Prompt层）
- 第3天：阶段3 + 全面测试

---
最后更新：2026-07-30
