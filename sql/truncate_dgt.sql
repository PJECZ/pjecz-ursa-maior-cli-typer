-- Truncar todas las tablas dgt_
-- Reinicia las secuencias de los id y respeta las llaves foraneas entre ellas
-- CASCADE tambien truncara cualquier otra tabla que tenga llaves foraneas hacia estas

BEGIN;

TRUNCATE TABLE
    dgt_depositos,
    dgt_digitalizaciones,
    dgt_digitalizaciones_bitacoras,
    dgt_entregas,
    dgt_entregas_bitacoras,
    dgt_plataformas,
    dgt_plataformas_autoridades,
    dgt_plataformas_endpoints,
    dgt_plataformas_endpoints_bitacoras,
    dgt_rutas,
    dgt_tipos
RESTART IDENTITY CASCADE;

COMMIT;
