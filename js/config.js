/*
  Configuración PÚBLICA del navegador (Etapa 3).

  Aquí solo van dos datos que cualquier visitante puede ver de todos modos:
    · la URL del proyecto de Supabase
    · la clave "publishable" (antes llamada "anon"), diseñada para ir en el navegador.
  La protección de los datos NO depende de ocultar esta clave: la dan las políticas
  de seguridad por filas (RLS) y las funciones del servidor instaladas en la Etapa 2.

  NUNCA pongas aquí: la "secret key" / "service_role", la contraseña de la base de datos,
  claves de Resend ni ningún token privado. Esos solo pueden vivir como secretos del servidor.
  (js/tp-client.js se niega a funcionar si detecta una clave secreta en este archivo.)
*/
window.TP_CONFIG = Object.freeze({
  SUPABASE_URL: 'https://mtkbxnhsjqqdbrjeaslo.supabase.co',
  SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_HqVlBYz_UizUGTe1iVu7tw_9GWv7-jm'
});
