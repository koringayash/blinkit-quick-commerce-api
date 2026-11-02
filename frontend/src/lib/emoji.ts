// The backend has no product images, so tiles show an icon picked from the category name.
const MAP: [RegExp, string][] = [
  [/dairy|milk|breakfast/i, "🥛"],
  [/bread|bakery/i, "🍞"],
  [/fruit/i, "🍎"],
  [/veg/i, "🥦"],
  [/snack|chip|munch/i, "🍿"],
  [/drink|beverage|juice/i, "🧃"],
  [/sweet|chocolate|candy/i, "🍫"],
  [/meat|chicken|fish|egg/i, "🍗"],
  [/clean|household/i, "🧴"],
  [/personal|care|beauty/i, "🧼"],
  [/baby/i, "🍼"],
  [/frozen|ice/i, "🍦"],
  [/tea|coffee/i, "☕"],
  [/atta|rice|dal|grain|staple/i, "🌾"],
];
export function categoryEmoji(cat: string | null | undefined) {
  if (!cat) return "🛒";
  return MAP.find(([r]) => r.test(cat))?.[1] ?? "🛒";
}
