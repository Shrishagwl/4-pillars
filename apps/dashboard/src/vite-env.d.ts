/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "api" to use the live backend; anything else (or unset) uses mock data. */
  readonly VITE_DATA_SOURCE?: string;
  /** ingest-api's base URL, e.g. http://localhost:8081. */
  readonly VITE_INGEST_URL?: string;
}
