-- Copy project data to create a demo project
-- Source project: 78047f9d-3d4e-404c-b9e1-34d5c40a6507 (ends in 507!)
-- This script creates a new demo project and copies all related data
-- IMPORTANT: The source project ID ends in 507, not 500!

-- Generate a new demo project ID (use this ID for VITE_DEMO_PROJECT_ID and DEMO_PROJECT_ID)
-- Demo project ID: 00000000-0000-0000-0000-000000000001 (easy to remember)

DO $$
DECLARE
    source_project_id UUID := '78047f9d-3d4e-404c-b9e1-34d5c40a650';
    demo_project_id UUID := '00000000-0000-0000-0000-000000000001';
    demo_user_id UUID := '00000000-0000-0000-0000-000000000000'; -- null/system user for demo
    disc_row RECORD;
    page_row RECORD;
    pointer_row RECORD;
    new_disc_id UUID;
    new_page_id UUID;
    new_pointer_id UUID;
    disc_id_map JSONB := '{}';
    page_id_map JSONB := '{}';
BEGIN
    -- Delete existing demo project if it exists (for re-running)
    DELETE FROM pointers WHERE page_id IN (SELECT id FROM pages WHERE project_id = demo_project_id);
    DELETE FROM pages WHERE project_id = demo_project_id;
    DELETE FROM disciplines WHERE project_id = demo_project_id;
    DELETE FROM projects WHERE id = demo_project_id;

    -- 1. Create demo project
    INSERT INTO projects (id, user_id, name, status, created_at, updated_at)
    VALUES (
        demo_project_id,
        demo_user_id,
        'Demo Project',
        'ready',
        NOW(),
        NOW()
    );
    RAISE NOTICE 'Created demo project: %', demo_project_id;

    -- 2. Copy disciplines
    FOR disc_row IN
        SELECT * FROM disciplines WHERE project_id = source_project_id
    LOOP
        new_disc_id := gen_random_uuid();
        disc_id_map := disc_id_map || jsonb_build_object(disc_row.id::text, new_disc_id::text);

        INSERT INTO disciplines (id, project_id, code, name, display_name, context_description, key_contents, connections, processed, created_at, updated_at)
        VALUES (
            new_disc_id,
            demo_project_id,
            disc_row.code,
            disc_row.name,
            disc_row.display_name,
            disc_row.context_description,
            disc_row.key_contents,
            disc_row.connections,
            disc_row.processed,
            NOW(),
            NOW()
        );
    END LOOP;
    RAISE NOTICE 'Copied % disciplines', (SELECT COUNT(*) FROM disciplines WHERE project_id = demo_project_id);

    -- 3. Copy pages
    FOR page_row IN
        SELECT * FROM pages WHERE project_id = source_project_id
    LOOP
        new_page_id := gen_random_uuid();
        page_id_map := page_id_map || jsonb_build_object(page_row.id::text, new_page_id::text);

        INSERT INTO pages (
            id, project_id, discipline_id, page_name, page_number, file_path,
            page_image_path, initial_context, processed_pass_1, processed_pass_2,
            pass_1_output, pass_2_output, created_at, updated_at
        )
        VALUES (
            new_page_id,
            demo_project_id,
            (disc_id_map ->> page_row.discipline_id::text)::UUID,
            page_row.page_name,
            page_row.page_number,
            page_row.file_path,
            page_row.page_image_path,
            page_row.initial_context,
            page_row.processed_pass_1,
            page_row.processed_pass_2,
            page_row.pass_1_output,
            page_row.pass_2_output,
            NOW(),
            NOW()
        );
    END LOOP;
    RAISE NOTICE 'Copied % pages', (SELECT COUNT(*) FROM pages WHERE project_id = demo_project_id);

    -- 4. Copy pointers
    FOR pointer_row IN
        SELECT p.* FROM pointers p
        JOIN pages pg ON p.page_id = pg.id
        WHERE pg.project_id = source_project_id
    LOOP
        new_pointer_id := gen_random_uuid();

        INSERT INTO pointers (
            id, page_id, title, description, text_spans, ocr_data,
            bbox_x, bbox_y, bbox_width, bbox_height, png_path,
            needs_embedding, created_at, updated_at
        )
        VALUES (
            new_pointer_id,
            (page_id_map ->> pointer_row.page_id::text)::UUID,
            pointer_row.title,
            pointer_row.description,
            pointer_row.text_spans,
            pointer_row.ocr_data,
            pointer_row.bbox_x,
            pointer_row.bbox_y,
            pointer_row.bbox_width,
            pointer_row.bbox_height,
            pointer_row.png_path,
            pointer_row.needs_embedding,
            NOW(),
            NOW()
        );
    END LOOP;
    RAISE NOTICE 'Copied % pointers', (SELECT COUNT(*) FROM pointers p JOIN pages pg ON p.page_id = pg.id WHERE pg.project_id = demo_project_id);

    RAISE NOTICE 'Demo project setup complete!';
    RAISE NOTICE 'Demo Project ID: %', demo_project_id;
END $$;

-- Verify the copy
SELECT 'projects' as table_name, COUNT(*) as count FROM projects WHERE id = '00000000-0000-0000-0000-000000000001'
UNION ALL
SELECT 'disciplines', COUNT(*) FROM disciplines WHERE project_id = '00000000-0000-0000-0000-000000000001'
UNION ALL
SELECT 'pages', COUNT(*) FROM pages WHERE project_id = '00000000-0000-0000-0000-000000000001'
UNION ALL
SELECT 'pointers', COUNT(*) FROM pointers p JOIN pages pg ON p.page_id = pg.id WHERE pg.project_id = '00000000-0000-0000-0000-000000000001';
