/**
 * JWT Helper - Manejo de tokens JWT en el frontend
 *
 * El token viaja exclusivamente en cookie HttpOnly — no se guarda en
 * localStorage ni se envía via header Authorization.
 * Este helper solo provee un fetch wrapper con credentials y manejo de 401.
 */

const JWTHelper = (() => {
    /**
     * Wrapper para fetch que envía la cookie HttpOnly automáticamente
     * y maneja redirección por sesión expirada.
     */
    const fetchWithToken = async (url, options = {}) => {
        const config = {
            ...options,
            headers: {
                ...options.headers,
                'Content-Type': 'application/json',
            },
            credentials: 'same-origin', // Envía la cookie HttpOnly
        };

        try {
            const response = await fetch(url, config);

            if (response.status === 401) {
                const data = await response.json();
                if (data.redirect) {
                    window.location.href = data.redirect;
                    return response;
                }
            }

            return response;
        } catch (error) {
            console.error('Error en fetchWithToken:', error);
            throw error;
        }
    };

    /**
     * Convierte FormData a JSON para enviarlo con JWT
     */
    const formDataToJSON = (formData) => {
        const object = {};
        formData.forEach((value, key) => {
            if (object[key]) {
                if (!Array.isArray(object[key])) {
                    object[key] = [object[key]];
                }
                object[key].push(value);
            } else {
                object[key] = value;
            }
        });
        return object;
    };

    return {
        fetchWithToken,
        formDataToJSON
    };
})();

window.JWTHelper = JWTHelper;
