#!/usr/bin/env python3
"""
Mizan Product Data Cleanup
Removes duplicates, fixes data quality issues, and filters incomplete products.
"""

import json
from pathlib import Path
import re

def normalize_name(name):
    """Normalize product name for duplicate detection."""
    name = name.lower().strip()
    # Remove common suffixes
    name = re.sub(r'\s*\d+\s*(g|gm|ml|l|kg|pack|pcs?|x\s*\d+).*$', '', name, flags=re.I)
    # Remove special chars
    name = re.sub(r'[^\w\s]', '', name)
    # Remove extra spaces
    name = re.sub(r'\s+', ' ', name)
    return name

def is_complete_product(product):
    """Check if product has enough data."""
    nutrients = product.get('nutrients', {})

    # Must have reasonable calorie value
    calories = nutrients.get('energy_kcal', 0)
    if calories < 10 or calories > 900:
        return False

    # Must have at least 2 other nutrients with non-zero values
    other_nutrients = [
        nutrients.get('protein_g', 0),
        nutrients.get('sugar_g', 0),
        nutrients.get('sodium_mg', 0),
        nutrients.get('total_fat_g', 0),
        nutrients.get('carbohydrates_g', 0)
    ]

    non_zero = sum(1 for n in other_nutrients if n > 0)
    if non_zero < 2:
        return False

    # Name must be meaningful (more than just brand name)
    name = product.get('name', '')
    if len(name) < 5:
        return False

    return True

def fix_product_name(product):
    """Clean up product name."""
    name = product.get('name', '')
    brand = product.get('brand', '')

    # Remove duplicate brand name
    if brand and name.lower().startswith(brand.lower()):
        name = name[len(brand):].strip(' -')
        name = f"{brand} {name}".strip()

    # Remove product codes
    name = re.sub(r'\s*\d{10,}', '', name)

    # Remove size info from name
    name = re.sub(r'\s*\d+\s*(g|gm|ml|l|kg)\s*(\(\d+\))?', '', name, flags=re.I)

    # Clean up extra spaces
    name = re.sub(r'\s+', ' ', name).strip()

    # Capitalize properly
    words = name.split()
    name = ' '.join(w.capitalize() if w.lower() not in ['and', 'or', 'the', 'of', 'in'] else w.lower() for w in words)

    product['name'] = name
    return product

def cleanup_products(input_path, output_path):
    """Clean up product data."""
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    products = data.get('products', [])
    print(f"Starting with {len(products)} products")

    # Step 1: Fix names
    products = [fix_product_name(p) for p in products]

    # Step 2: Filter incomplete products
    complete_products = [p for p in products if is_complete_product(p)]
    print(f"After filtering incomplete: {len(complete_products)} products")

    # Step 3: Remove duplicates (keep first occurrence with best data)
    seen_names = {}
    unique_products = []

    for product in complete_products:
        norm_name = normalize_name(product['name'])

        if norm_name in seen_names:
            # Keep the one with more nutrients data
            existing = seen_names[norm_name]
            existing_nutrients = sum(1 for v in existing['nutrients'].values() if v > 0)
            new_nutrients = sum(1 for v in product['nutrients'].values() if v > 0)

            if new_nutrients > existing_nutrients:
                # Replace with better data
                idx = unique_products.index(existing)
                unique_products[idx] = product
                seen_names[norm_name] = product
        else:
            seen_names[norm_name] = product
            unique_products.append(product)

    print(f"After removing duplicates: {len(unique_products)} products")

    # Step 4: Regenerate slugs to avoid conflicts
    used_slugs = set()
    for product in unique_products:
        base_slug = re.sub(r'[^\w\s-]', '', product['name'].lower())
        base_slug = re.sub(r'[\s_-]+', '-', base_slug).strip('-')

        slug = base_slug
        counter = 1
        while slug in used_slugs:
            slug = f"{base_slug}-{counter}"
            counter += 1

        product['slug'] = slug
        used_slugs.add(slug)

    # Save cleaned data
    data['products'] = unique_products
    data['count'] = len(unique_products)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(unique_products)} cleaned products to {output_path}")

    # Print summary by category
    categories = {}
    for p in unique_products:
        cat = p.get('category_slug', 'other')
        categories[cat] = categories.get(cat, 0) + 1

    print("\nProducts by category:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    return unique_products

if __name__ == "__main__":
    script_dir = Path(__file__).parent
    input_path = script_dir.parent / "src" / "data" / "products_raw.json"
    output_path = script_dir.parent / "src" / "data" / "products_clean.json"

    cleanup_products(input_path, output_path)
