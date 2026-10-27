-- Datos de muestra para pruebas de las tablas dgt_
-- No se insertan registros en dgt_entregas, dgt_digitalizaciones ni en las *_bitacoras
-- Requiere que exista la autoridad SLT-J2-MER en la tabla autoridades
-- Se usan UUID fijos para que las llaves foraneas sean legibles

BEGIN;

-- Tipos
INSERT INTO dgt_tipos (id, clave, descripcion, estatus) VALUES
    ('00000000-0000-0000-0000-000000000101', 'EXP', 'EXPEDIENTES', 'A');

-- Depositos, la clave en minusculas es el nombre del bucket
INSERT INTO dgt_depositos (id, clave, descripcion, proposito, estatus) VALUES
    ('00000000-0000-0000-0000-000000000201', 'PJECZ-CONSULTAS', 'DEPOSITO DE PRUEBAS PARA ENTREGAS', 'ENTREGAS', 'A'),
    ('00000000-0000-0000-0000-000000000202', 'PJECZ-INFORMATICA', 'DEPOSITO DE PRUEBAS PARA DIGITALIZACIONES', 'DIGITALIZACIONES', 'A');

-- Rutas, una por cada deposito
INSERT INTO dgt_rutas (id, dgt_deposito_id, dgt_tipo_id, clave, autoridad_clave, directorio, estatus) VALUES
    ('00000000-0000-0000-0000-000000000301', '00000000-0000-0000-0000-000000000201', '00000000-0000-0000-0000-000000000101', 'PJECZ-CONSULTAS-SLT-J2-MER', 'SLT-J2-MER', 'dgt_entregas/SLT-J2-MER', 'A'),
    ('00000000-0000-0000-0000-000000000302', '00000000-0000-0000-0000-000000000202', '00000000-0000-0000-0000-000000000101', 'PJECZ-INFORMATICA-SLT-J2-MER', 'SLT-J2-MER', 'dgt_digitalizaciones/SLT-J2-MER', 'A');

-- Plataformas
INSERT INTO dgt_plataformas (id, clave, descripcion, api_key, estatus) VALUES
    ('00000000-0000-0000-0000-000000000401', 'SAJI PRUEBAS', 'SAJI PLATAFORMA DE PRUEBAS', 'prueba-api-key-0123456789abcdef', 'A');

-- Plataformas Autoridades
INSERT INTO dgt_plataformas_autoridades (id, autoridad_id, dgt_plataforma_id, estatus)
SELECT '00000000-0000-0000-0000-000000000501', id, '00000000-0000-0000-0000-000000000401', 'A'
FROM autoridades
WHERE clave = 'SLT-J2-MER';

-- Plataformas Endpoints
INSERT INTO dgt_plataformas_endpoints (id, dgt_plataforma_id, descripcion, ruta, proposito, metodo, payload_muestra, estatus) VALUES
    (
        '00000000-0000-0000-0000-000000000601',
        '00000000-0000-0000-0000-000000000401',
        'INSERTAR DIGITALIZACIONES',
        'http://localhost:8000/api/v1/digitalizaciones',
        'INSERTAR',
        'POST',
        '{"digitalizaciones": [{"autoridadClave": "SLT-J2-MER", "numeroExpediente": "123/2026", "url": "https://storage.googleapis.com/pjecz-pruebas-digitalizaciones/SLT-J2-MER/EXHORTOS/archivo.pdf"}]}',
        'A'
    );

COMMIT;
