export default [
  { ignores: ['dist/**', 'node_modules/**', 'coverage/**', 'data/*.db'] },
  { files: ['**/*.js','**/*.ts'], languageOptions: { ecmaVersion: 2022, sourceType: 'module' }, rules: {} },
];
