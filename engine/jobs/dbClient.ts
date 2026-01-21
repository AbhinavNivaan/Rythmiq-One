
import { createClient, SupabaseClient } from '@supabase/supabase-js';
import { getConfig } from '../../bootstrap/config';

let client: SupabaseClient | null = null;

export function getSupabaseClient(): SupabaseClient {
    if (client) return client;

    const config = getConfig();
    if (!config.databaseUrl && !process.env.SUPABASE_URL) {
        throw new Error('Missing SUPABASE_URL or DATABASE_URL for Supabase client');
    }

    const url = process.env.SUPABASE_URL || config.databaseUrl;
    const key = process.env.SUPABASE_SERVICE_KEY || process.env.SUPABASE_KEY;

    if (!url || !key) {
        throw new Error('Supabase URL and Key are required');
    }

    client = createClient(url, key);
    return client;
}
