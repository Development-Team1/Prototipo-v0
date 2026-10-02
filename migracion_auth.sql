-- Ejecutar UNA vez en Supabase: SQL Editor > New query > Run.
-- Agrega lo necesario para el login y para que cada evento tenga dueño.

-- 1) Contraseña (hash bcrypt) de cada usuario
ALTER TABLE "user" ADD COLUMN IF NOT EXISTS password_hash varchar(255);

-- 2) Dueño de cada evento
ALTER TABLE events
  ADD COLUMN IF NOT EXISTS user_id bigint
  REFERENCES "user"(user_id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS ix_events_user_id ON events(user_id);

-- OPCIONAL: los eventos y usuarios de prueba creados antes del login no tienen
-- contraseña ni dueño, así que nadie los verá. Si quieres limpiarlos:
-- DELETE FROM events WHERE user_id IS NULL;
-- DELETE FROM "user" WHERE password_hash IS NULL;
