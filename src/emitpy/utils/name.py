# CamelName to camel_name
def CamelToSnake(s):
    return ''.join(['_'+i.lower() if i.isupper() else i for i in s]).lstrip('_')

# camel_name to CamelName
def SnakeToCamel(s):
    return ''.join(map(str.title, s.split('_')))

# CamelName to camel-name
def CamelToKebab(s):
    return ''.join(['-'+i.lower() if i.isupper() else i for i in s]).lstrip('-')

# camel-name to CamelName
def KebabToCamel(s):
    return ''.join(map(str.title, s.split('-')))
