# Tale-AI 适配器层

**FileAttachment**:
文件附件，包含文件名、下载URL和可选的文件大小。
_Avoid_: file, attachment

**ProcessedMessage**:
经过权限检查和决策处理后的标准化消息，由 MessageProcessor 生成。
_Avoid_: handled message

**PlatformEvent**:
适配器将平台原始事件转换后的统一格式。
_Avoid_: raw event, adapter event
