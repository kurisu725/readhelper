"""Shared research mode and stable labels for saved analyses."""
GENERAL = {'innovations':'创新点','improvements':'可改进方向','takeaways':'可学习与参考之处'}
HISTORY = {'innovations':'历史贡献、时代语境与后世影响','improvements':'解释局限、证据缺口与待考证问题','takeaways':'研究方法、史料线索与比较对象'}


def mode(value, app):
    if value not in ('general','history'):
        raise app.AppError('请选择通用研读或建筑史研究模式。')
    return value


def labels(value):
    return HISTORY if value == 'history' else GENERAL


def instruction(value):
    if value != 'history': return ''
    return '''\n建筑史研究模式（architecture_history）：按以下研究视角解释分析栏目，JSON字段名与引用格式保持原协议。
innovations对应“历史贡献、时代语境与后世影响”；improvements对应“解释局限、证据缺口与待考证问题”；takeaways对应“研究方法、史料线索与比较对象”。
区分建筑发生的年代、史料形成的年代与研究发表的年代；保留原纪年、约年、年代范围及异说，不擅自换算或合并成精确年份。
明确区分史料原文、作者论断和分析推测；在提供的材料中追踪引证与转引，共引同一史源不能直接当作独立互证。
历史贡献和影响关系需要来源证据；形式相似只可提出比较线索，不能证明传播或师承。结合当时语境解释，避免用当代设计标准直接判断历史建筑优劣。
缺失的作者、营造者、年代、版本、档案号和因果关系必须标为待考证，不补造史实、引文或图像细节。'''
