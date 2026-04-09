-- Migration 015: add body_color to trainer_settings table
--
-- Business reason:
--   The trainer can now customize the general app background color
--   (body background) independently from the primary color (sidebar, buttons).
--   Example: blue sidebar with dark-grey body.
--
-- Nullable field — existing trainers will have NULL (uses the app's default theme).
 
ALTER TABLE trainer_settings
  ADD COLUMN IF NOT EXISTS body_color VARCHAR(7) NULL;
 
COMMENT ON COLUMN trainer_settings.body_color IS
  'Hex color for the general app background (body/background). NULL = uses the default theme.';