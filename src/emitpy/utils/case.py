# Convert strings between different case patterns


def CamelToSnake(s):
    """CamelName to camel_name"""
    return "".join(["_" + i.lower() if i.isupper() else i for i in s]).lstrip("_")


def SnakeToCamel(s):
    """camel_name to CamelName"""
    return "".join(map(str.title, s.split("_")))


def CamelToKebab(s):
    """CamelName to camel-name"""
    return "".join(["-" + i.lower() if i.isupper() else i for i in s]).lstrip("-")


def KebabToCamel(s):
    """camel-name to CamelName"""
    return "".join(map(str.title, s.split("-")))
