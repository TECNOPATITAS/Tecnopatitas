/*
  Configuración PÚBLICA del navegador (Etapa 3).

  Aquí solo van dos datos que cualquier visitante puede ver de todos modos:
    · la URL del proyecto de Supabase
    · la clave "publishable" (antes llamada "anon"), diseñada para ir en el navegador.
  La protección de los datos NO depende de ocultar esta clave: la dan las políticas
  de seguridad por filas (RLS) y las funciones del servidor instaladas en la Etapa 2.

  Etapa 6: también va aquí la «site key» (clave de sitio) de Cloudflare Turnstile. Es PÚBLICA por diseño (aparece en
  el código de cualquier página que use Turnstile). La «secret key» de Turnstile NO va aquí jamás: se guarda como secreto
  de la función segura en Supabase (ver GUIA_ETAPA_6.md).

  NUNCA pongas aquí: la "secret key" / "service_role", la contraseña de la base de datos,
  claves de Resend ni ningún token privado. Esos solo pueden vivir como secretos del servidor.
  (js/tp-client.js se niega a funcionar si detecta una clave secreta en este archivo.)
*/
window.TP_CONFIG = Object.freeze({
  SUPABASE_URL: 'https://mtkbxnhsjqqdbrjeaslo.supabase.co',
  SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_HqVlBYz_UizUGTe1iVu7tw_9GWv7-jm',
  TURNSTILE_SITE_KEY: '0x4AAAAAAF0HtqWbA1_WsqN4'          // ← pega aquí tu «Site Key» de Cloudflare Turnstile (empieza con 0x4…). Vacío = sin anti-robots y sin denuncias.
});
