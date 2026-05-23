// SPDX-License-Identifier: Apache-2.0
// Part of @axxis/oracle — https://github.com/dot-protocol/oracle-sdk-ts

import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['test/**/*.test.ts'],
    environment: 'node',
    globals: false,
  },
});
