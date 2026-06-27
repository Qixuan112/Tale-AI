"""
安全计算器 - 替代 eval() 的数学表达式求值

支持基本运算符：+ - * / // % ** ( )
支持函数：abs, round, max, min, sum, pow, int, float
"""
import ast
import builtins
import operator
from typing import Union, Any


# 幂运算限制：防止 9**9**9 / 2**99999999 这类表达式阻塞事件循环或耗尽内存
_MAX_POW_EXPONENT = 1000          # 指数绝对值上限
_MAX_POW_BASE = 10 ** 6           # 底数绝对值上限
_MAX_POW_RESULT_BITS = 4096       # 结果位长上限（约 1233 位十进制数）


def _safe_pow(base, exp):
    """
    受限的幂运算，超出限制时抛出 ValueError（由上层错误处理转为普通计算错误）

    限制：指数绝对值 <= 1000，底数绝对值 <= 1e6，结果位长 <= 4096 位
    """
    # 指数绝对值过大直接拒绝
    if abs(exp) > _MAX_POW_EXPONENT:
        raise ValueError(f"指数过大（绝对值上限 {_MAX_POW_EXPONENT}）")
    # 底数绝对值过大且指数会放大时拒绝
    if abs(base) > _MAX_POW_BASE and abs(exp) > 1:
        raise ValueError(f"底数过大（绝对值上限 {_MAX_POW_BASE}）")
    result = operator.pow(base, exp)
    # 整数结果位长超限时拒绝，避免巨型整数运算
    if isinstance(result, int) and result.bit_length() > _MAX_POW_RESULT_BITS:
        raise ValueError(f"计算结果过大（位长上限 {_MAX_POW_RESULT_BITS}）")
    return result


# 支持的运算符映射
_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: _safe_pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# 允许调用的函数（白名单）
_ALLOWED_FUNCTIONS = {
    "abs", "round", "max", "min", "sum", "pow",
    "int", "float", "len",
}


def safe_eval(expression: str) -> Union[int, float]:
    """
    安全地求值数学表达式

    Args:
        expression: 数学表达式字符串，如 "1+2*3"

    Returns:
        计算结果（int 或 float）

    Raises:
        ValueError: 表达式包含不允许的语法
        SyntaxError: 表达式语法错误
        ZeroDivisionError: 除零错误
    """
    if not expression or not expression.strip():
        raise ValueError("表达式不能为空")

    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as e:
        raise SyntaxError(f"表达式语法错误: {e}") from e

    result = _eval_node(tree.body)
    return result


def _eval_node(node: ast.AST) -> Any:
    """递归求值 AST 节点"""
    # 常量（Python 3.8+）
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"不支持的常量类型: {type(node.value).__name__}")

    # 数字字面量（兼容旧版 Python）
    if isinstance(node, ast.Num):
        return node.n

    # 二元运算：a + b
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _OPERATORS:
            raise ValueError(f"不支持的运算符: {op_type.__name__}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return _OPERATORS[op_type](left, right)

    # 一元运算：-a, +a
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _OPERATORS:
            raise ValueError(f"不支持的一元运算符: {op_type.__name__}")
        operand = _eval_node(node.operand)
        return _OPERATORS[op_type](operand)

    # 函数调用：abs(-5)
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("只允许调用简单函数名")
        func_name = node.func.id
        if func_name not in _ALLOWED_FUNCTIONS:
            raise ValueError(f"不允许调用的函数: {func_name}")

        args = [_eval_node(arg) for arg in node.args]
        kwargs = {kw.arg: _eval_node(kw.value) for kw in node.keywords}

        # pow 函数走受限实现，防止 pow(2, 99999999) 这类 DoS
        if func_name == "pow":
            if kwargs or len(args) != 2:
                raise ValueError("pow 仅支持两个位置参数")
            return _safe_pow(args[0], args[1])

        import builtins
        # 获取内置函数
        func = getattr(builtins, func_name)
        return func(*args, **kwargs)

    # 表达式元组（如 (1, 2) 在函数调用中）
    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(elt) for elt in node.elts)

    # 列表字面量
    if isinstance(node, ast.List):
        return [_eval_node(elt) for elt in node.elts]

    raise ValueError(f"不支持的表达式类型: {type(node).__name__}")


def safe_calculate(expression: str) -> dict:
    """
    安全计算并返回标准格式的结果字典

    Args:
        expression: 数学表达式

    Returns:
        {"status": "success", "result": 值} 或 {"status": "failed", "error": 错误信息}
    """
    try:
        result = safe_eval(expression)
        return {
            "status": "success",
            "tool": "calculator",
            "expression": expression,
            "result": result,
        }
    except ZeroDivisionError:
        return {"status": "failed", "tool": "calculator", "error": "除零错误"}
    except Exception as e:
        return {"status": "failed", "tool": "calculator", "error": str(e)}
