# Code health, the mobile half: sourced by selftest.sh's --mobile pass with cwd = the
# real Expo app ($M/mobile) after `npm run gates` went green there. knip and the ESLint
# complexity rules each FAIL, naming their rule, on a planted violation.

cp lib/app.ts "$T/ch-app.ts"
printf '\nexport function plantedUnused(): number {\n  return 1;\n}\n' >> lib/app.ts
refuses "knip catches an unused export" "npx knip" "plantedUnused"
cp "$T/ch-app.ts" lib/app.ts

{
  printf 'export function planted(x: number): number {\n'
  for i in $(seq 0 15); do printf '  if (x === %s) return %s;\n' "$i" "$i"; done
  printf '  return -1;\n}\n'
} > lib/planted-complex.ts
refuses "eslint catches a function over the complexity limit" "npx eslint lib/planted-complex.ts" "complexity"
rm -f lib/planted-complex.ts
