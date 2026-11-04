-- =====================================================================
-- TECNOPATITAS · Etapa 2 · 06 · DATOS DE DEMOSTRACIÓN (OPCIONAL)
--
-- • Seis establecimientos FICTICIOS marcados is_demo = true. No tienen
--   teléfono, dueño ni etiqueta de verificación. Para quitarlos después:
--       delete from public.businesses where is_demo;
-- • Ocho guías de cuidado de carácter GENERAL, con la fuente indicada como
--   "pendiente de revisión veterinaria". Revísalas y reemplázalas desde el
--   panel de administración (Etapa 10) antes de presentarlas como definitivas.
-- Se puede ejecutar más de una vez.
-- =====================================================================

delete from public.businesses where is_demo;
insert into public.businesses (is_demo, owner_id, name, category, description, address, state, municipality, status) values
(true, null, 'Veterinaria Ejemplo Uno',      'veterinaria',     'Ficha de demostración. Aquí irá la descripción de una veterinaria real.', 'Dirección de ejemplo', 'Estado de ejemplo', 'Municipio de ejemplo', 'approved'),
(true, null, 'Clínica Demo Huellas',         'veterinaria',     'Ficha de demostración de una clínica con servicio de urgencias.',          'Dirección de ejemplo', 'Estado de ejemplo', 'Municipio de ejemplo', 'approved'),
(true, null, 'Estética Canina Ejemplo',      'estetica_canina', 'Ficha de demostración de una estética para perros.',                       'Dirección de ejemplo', 'Estado de ejemplo', 'Municipio de ejemplo', 'approved'),
(true, null, 'Gatitos Demo Spa',             'estetica_felina', 'Ficha de demostración de una estética para gatos.',                        'Dirección de ejemplo', 'Estado de ejemplo', 'Municipio de ejemplo', 'approved'),
(true, null, 'Tienda Mascotas Ejemplo',      'tienda',          'Ficha de demostración de una tienda de alimento y accesorios.',            'Dirección de ejemplo', 'Estado de ejemplo', 'Municipio de ejemplo', 'approved'),
(true, null, 'Adiestramiento Demo',          'adiestramiento',  'Ficha de demostración de un servicio de adiestramiento.',                  'Dirección de ejemplo', 'Estado de ejemplo', 'Municipio de ejemplo', 'approved');

insert into public.care_guides (slug, title, summary, category, author_source, is_published, content) values
('cuidados-basicos-para-un-perro', 'Cuidados básicos para un perro',
 'Rutina, paseos y atención diaria para un perro sano y tranquilo.', 'perros',
 'Contenido general de ejemplo, pendiente de revisión veterinaria', true,
$g$Un perro necesita agua fresca disponible todo el día, alimento adecuado a su edad, tamaño y nivel de actividad, y espacio para moverse. Los paseos diarios y el juego ayudan a gastar energía y reducen el estrés.

Mantener horarios estables de comida, paseo y descanso le da seguridad. Socializarlo con calma, con otras personas y otros perros, desde cachorro, facilita su convivencia.

Revisa con regularidad sus orejas, dientes, patas y piel. Si notas cambios que te preocupen, consulta a un veterinario: esta guía es información general y no sustituye una consulta profesional.$g$),

('como-preparar-tu-hogar-para-un-gato', 'Cómo preparar tu hogar para un gato',
 'Espacios seguros y enriquecimiento para un gato en casa.', 'gatos',
 'Contenido general de ejemplo, pendiente de revisión veterinaria', true,
$g$Los gatos necesitan un arenero limpio y accesible, rascadores, lugares altos para descansar y un refugio tranquilo donde puedan esconderse. Coloca el arenero lejos de su comida y agua.

Revisa que no estén a su alcance plantas tóxicas, cables, hilos u objetos pequeños que pueda tragar. Protege ventanas y balcones con mallas para evitar caídas.

Dedica tiempo diario al juego: ayuda a prevenir el aburrimiento y el sobrepeso. Ante cualquier duda de salud, consulta a un veterinario; esta guía es solo orientativa.$g$),

('cuidados-basicos-para-aves-de-compania', 'Cuidados básicos para aves de compañía',
 'Jaula, alimentación y descanso para aves en casa.', 'aves',
 'Contenido general de ejemplo, pendiente de revisión veterinaria', true,
$g$Elige una jaula amplia, límpiala con frecuencia y colócala lejos de corrientes de aire, del sol directo intenso y de la cocina, donde los humos pueden dañarlas.

Ofrece una dieta variada recomendada para su especie, agua limpia todos los días y periodos de descanso en un lugar tranquilo, sin ruido.

Las aves ocultan sus molestias. Si notas plumas erizadas, poco apetito o decaimiento, acude con un veterinario especializado. Esta guía es información general.$g$),

('conejos-y-pequenos-mamiferos', 'Conejos y pequeños mamíferos',
 'Espacio, heno y enriquecimiento para conejos y roedores.', 'conejos',
 'Contenido general de ejemplo, pendiente de revisión veterinaria', true,
$g$Los conejos necesitan espacio para correr y saltar, heno disponible todo el día y agua limpia. Ofrece escondites y objetos seguros para roer, ya que sus dientes crecen de forma continua.

Evita cambios bruscos de temperatura y no los dejes solos al sol. Cada especie tiene necesidades distintas, así que infórmate sobre la tuya.

Para vacunas, desparasitación y revisiones, busca a un veterinario con experiencia en animales exóticos o pequeños mamíferos. Esta guía es información general.$g$),

('mantener-hidratada-a-tu-mascota', 'Recomendaciones para mantener hidratada a tu mascota',
 'Agua limpia todos los días y señales a vigilar.', 'alimentacion',
 'Contenido general de ejemplo, pendiente de revisión veterinaria', true,
$g$Cambia el agua todos los días, lava el bebedero y deja varios puntos de agua en casa. A algunas mascotas les gusta más el agua en movimiento, como una fuente para gatos.

En días de calor ofrece sombra, evita paseos en las horas más calurosas y nunca los dejes dentro de un vehículo.

Si tu mascota bebe mucho menos o mucho más de lo habitual, consulta a tu veterinario: puede ser una señal de que algo no va bien. Esta guía es orientativa.$g$),

('higiene-y-cuidado-del-pelaje', 'Consejos de higiene y cuidado del pelaje',
 'Cepillado, baño y revisiones sencillas en casa.', 'higiene',
 'Contenido general de ejemplo, pendiente de revisión veterinaria', true,
$g$Cepilla el pelaje con la frecuencia que pida su tipo de pelo para evitar nudos y retirar pelo suelto. Aprovecha para revisar la piel en busca de heridas, enrojecimiento o parásitos.

Báñalo solo cuando haga falta, con productos pensados para mascotas, y sécalo bien, sobre todo entre los pliegues y las orejas.

El corte de uñas y la limpieza de oídos requieren cuidado. Si no tienes experiencia, pide a tu veterinario o a una estética que te enseñe. Esta guía es información general.$g$),

('vacunas-y-desparasitacion', 'La importancia de las vacunas y la desparasitación',
 'Prevención con acompañamiento de tu veterinario.', 'vacunacion',
 'Contenido general de ejemplo, pendiente de revisión veterinaria', true,
$g$Las vacunas y la desparasitación ayudan a prevenir enfermedades que pueden ser graves tanto para tu mascota como, en algunos casos, para las personas.

Tu veterinario define el calendario según la especie, la edad y el estilo de vida de tu mascota. Anota las fechas de cada aplicación y de la próxima dosis para no olvidarlas.

No des medicamentos ni antiparasitarios sin indicación veterinaria: las dosis dependen del peso y de la especie. Esta guía es información general.$g$),

('senales-de-alerta-en-la-salud', 'Cómo identificar señales de alerta en la salud de una mascota',
 'Cambios que conviene consultar con un veterinario.', 'salud-preventiva',
 'Contenido general de ejemplo, pendiente de revisión veterinaria', true,
$g$Conoce lo normal en tu mascota para detectar cambios: apetito, energía, peso, heces, respiración y comportamiento. Los cambios sostenidos merecen atención.

Acude pronto con un veterinario si notas vómito o diarrea persistentes, dificultad para respirar, dolor, cojera, decaimiento marcado o si tu mascota no come ni bebe.

Esta guía no ofrece diagnósticos ni sustituye la consulta profesional. Ante una emergencia, ve de inmediato a una clínica veterinaria.$g$)
on conflict (slug) do update set
  title = excluded.title, summary = excluded.summary, category = excluded.category,
  author_source = excluded.author_source, is_published = excluded.is_published, content = excluded.content;
