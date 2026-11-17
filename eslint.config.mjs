import nextConfig from "eslint-config-next";

export default [
  ...nextConfig,
  {
    rules: {
      "react-hooks/purity": "warn",
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/refs": "warn",
    },
  },
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "backend/**",
      "scripts/**",
      "out/**",
      "*.config.mjs",
    ],
  },
];
