"""
Exceptions
"""

class MyAnyError(Exception):
    """Base exception class"""


class MyNotValidParamError(MyAnyError):
    """Excepción porque un parámetro es inválido"""
