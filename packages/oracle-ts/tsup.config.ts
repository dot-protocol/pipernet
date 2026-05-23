// SPDX-License-Identifier: Apache-2.0
// Part of @axxis/oracle — https://github.com/dot-protocol/oracle-sdk-ts

import { defineConfig } from 'tsup';

export default defineConfig({
  entry: ['src/index.ts'],
  format: ['esm', 'cjs'],
  dts: true,
  target: 'node18',
  clean: true,
  sourcemap: true,
  splitting: false,
  minify: false,
});
