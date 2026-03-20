/**
 * JWT Helper - Manejo de tokens JWT en el frontend
 * 
 * Este módulo proporciona funciones para trabajar con JWT tokens
 * que son enviados por el backend. Los tokens se almacenan en cookies
 * pero este helper también puede guardarlos en localStorage como backup.
 */

const JWTHelper = (() => {
    const TOKEN_KEY = 'torneo_token';
    
    /**
     * Obtiene el token desde localStorage (backup, ya que la cookie principal)
     */
    const getToken = () => {
        return localStorage.getItem(TOKEN_KEY);
    };
    
    /**
     * Guarda el token en localStorage
     */
    const setToken = (token) => {
        if (token) {
            localStorage.setItem(TOKEN_KEY, token);
        }
    };
    
    /**
     * Elimina el token
     */
    const removeToken = () => {
        localStorage.removeItem(TOKEN_KEY);
    };
    
    /**
     * Wrapper para fetch que maneja automáticamente los tokens JWT
     * 
     * @param {string} url - URL a la que hacer la petición
     * @param {object} options - Opciones de fetch
     * @returns {Promise<Response>}
     */
    const fetchWithToken = async (url, options = {}) => {
        // Configuración por defecto
        const config = {
            ...options,
            headers: {
                ...options.headers,
                'Content-Type': 'application/json',
            },
            credentials: 'same-origin', // Importante para enviar cookies
        };
        
        // Si hay un token en localStorage, agregarlo al header como backup
        const token = getToken();
        if (token) {
            config.headers['Authorization'] = `Bearer ${token}`;
        }
        
        try {
            const response = await fetch(url, config);
            
            // Verificar si la respuesta indica que la sesión expiró
            if (response.status === 401) {
                const data = await response.json();
                if (data.redirect) {
                    // Redirigir al login
                    window.location.href = data.redirect;
                    return response;
                }
            }
            
            // Si la respuesta incluye un token en el JSON, guardarlo
            if (response.ok) {
                const contentType = response.headers.get('content-type');
                if (contentType && contentType.includes('application/json')) {
                    const clone = response.clone();
                    const data = await clone.json();
                    if (data.token) {
                        setToken(data.token);
                    }
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
            // Si la clave ya existe, convertirla en array
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
    
    // Exponer API pública
    return {
        getToken,
        setToken,
        removeToken,
        fetchWithToken,
        formDataToJSON
    };
})();

// Hacer disponible globalmente
window.JWTHelper = JWTHelper;
