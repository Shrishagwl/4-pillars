import { defineConfig } from 'vitest/config';

export default defineConfig({
  // The database tests share one Postgres schema, so test files run one at a time.
  test: { fileParallelism: false },
});
