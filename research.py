"""Discipline-independent analysis API; specialties provide their own labels and prompt."""
import plugin_manager

GENERAL = {'innovations': '创新点', 'improvements': '可改进方向', 'takeaways': '可学习与参考之处'}


def mode(value, app):
    with app.connect() as conn:
        if not plugin_manager.available_mode(conn, value):
            raise app.AppError('请先启用对应的研究插件，或选择通用研读。')
    return value


def labels(value):
    _, mod = plugin_manager.provider(value)
    return mod.labels(value) if mod else GENERAL


def instruction(value):
    _, mod = plugin_manager.provider(value)
    return mod.instruction(value) if mod else ''
