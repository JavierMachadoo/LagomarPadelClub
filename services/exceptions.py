class ServiceError(Exception):
    """Error de lógica de negocio.

    Los route handlers lo capturan y devuelven la respuesta HTTP apropiada:

        try:
            result = some_service.do_something(...)
        except ServiceError as e:
            return jsonify({'error': e.message}), e.status_code
    """

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)
