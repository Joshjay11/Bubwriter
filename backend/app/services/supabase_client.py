"""Supabase client initialization.

Provides a configured Supabase client using the service role key
for backend operations that bypass RLS (admin actions like
webhook-triggered subscription updates).
"""

from supabase import Client, create_client

from app.config import settings


def get_supabase_client() -> Client:
    """Create and return a Supabase client with service role credentials."""
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )
