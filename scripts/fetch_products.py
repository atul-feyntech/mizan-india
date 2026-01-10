#!/usr/bin/env python3
"""
Mizan Product Fetcher
Fetches real Indian packaged food products from Open Food Facts API.

Usage:
    python scripts/fetch_products.py [--limit 100] [--output products.json]
"""

import json
import urllib.request
import urllib.parse
import time
import argparse
import re
from pathlib import Path

# Open Food Facts API
OFF_API_BASE = "https://world.openfoodfacts.org"

# Popular Indian brands to search for
INDIAN_BRANDS = [
    "Maggi", "Nestle", "Parle", "Britannia", "Amul", "Haldiram",
    "ITC", "Bournvita", "Horlicks", "Cadbury", "Lay's", "Kurkure",
    "Pepsi", "Coca-Cola", "Thums Up", "Tropicana", "Real", "Frooti",
    "Maaza", "Sprite", "Fanta", "Limca", "Glucon-D", "Tang",
    "Kellogg's", "Quaker", "Saffola", "Fortune", "Aashirvaad",
    "MTR", "Gits", "Bikano", "Balaji", "Bingo", "Uncle Chipps",
    "Hide & Seek", "Good Day", "Oreo", "Marie Gold", "50-50",
    "Krackjack", "Monaco", "Tiger", "Nutella", "Kissan", "Maggi",
    "Knorr", "Ching's", "Yippee", "Top Ramen", "Wai Wai",
    "Mother Dairy", "Nandini", "Verka", "Milma", "Aavin"
]

# Categories mapping
CATEGORY_MAP = {
    "noodles": "ready-to-eat",
    "instant": "ready-to-eat",
    "biscuits": "biscuits",
    "cookies": "biscuits",
    "chips": "namkeen",
    "snacks": "namkeen",
    "namkeen": "namkeen",
    "beverages": "drinks",
    "drinks": "drinks",
    "juice": "drinks",
    "soda": "drinks",
    "cola": "drinks",
    "soft drink": "drinks",
    "chocolate": "meetha",
    "candy": "meetha",
    "sweets": "meetha",
    "dairy": "dairy",
    "milk": "dairy",
    "butter": "dairy",
    "cheese": "dairy",
    "yogurt": "dairy",
    "curd": "dairy",
    "cereal": "nashta",
    "breakfast": "nashta",
    "oats": "nashta",
    "muesli": "nashta",
    "spread": "nashta",
    "jam": "nashta",
    "health drink": "bachon-ke-liye",
    "malt": "bachon-ke-liye",
}

def slugify(text):
    """Convert text to URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    text = re.sub(r'^-+|-+$', '', text)
    return text

def get_category(product_data):
    """Determine category from product data."""
    categories = product_data.get('categories', '').lower()
    product_name = product_data.get('product_name', '').lower()

    for keyword, category in CATEGORY_MAP.items():
        if keyword in categories or keyword in product_name:
            return category

    return "namkeen"  # Default

def search_products(query, page=1, page_size=50):
    """Search Open Food Facts for products."""
    params = {
        'search_terms': query,
        'search_simple': 1,
        'action': 'process',
        'json': 1,
        'page': page,
        'page_size': page_size,
        'countries_tags_en': 'india',
        'fields': 'code,product_name,brands,categories,nutriments,serving_size,ingredients_text,image_url,quantity'
    }

    url = f"{OFF_API_BASE}/cgi/search.pl?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mizan/1.0 (https://mizan.live)')

        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get('products', [])
    except Exception as e:
        print(f"Error searching for {query}: {e}")
        return []

def parse_quantity(quantity_str):
    """Parse quantity string to get package size in grams."""
    if not quantity_str:
        return 100

    quantity_str = quantity_str.lower()

    # Try to extract number and unit
    match = re.search(r'(\d+(?:\.\d+)?)\s*(g|gm|gram|ml|l|kg)', quantity_str)
    if match:
        value = float(match.group(1))
        unit = match.group(2)

        if unit in ['kg']:
            return value * 1000
        elif unit in ['l']:
            return value * 1000  # Approximate ml as g
        else:
            return value

    return 100

def extract_nutrients(nutriments):
    """Extract and normalize nutrients from Open Food Facts data."""
    def get_value(key, default=0):
        # Try _100g first, then base value
        val = nutriments.get(f'{key}_100g', nutriments.get(key, default))
        try:
            return round(float(val), 1) if val else default
        except (ValueError, TypeError):
            return default

    return {
        "energy_kcal": get_value('energy-kcal', get_value('energy', 0) / 4.184),  # kJ to kcal
        "protein_g": get_value('proteins'),
        "carbohydrates_g": get_value('carbohydrates'),
        "sugar_g": get_value('sugars'),
        "total_fat_g": get_value('fat'),
        "saturated_fat_g": get_value('saturated-fat'),
        "fiber_g": get_value('fiber'),
        "sodium_mg": get_value('sodium') * 1000 if get_value('sodium') < 10 else get_value('sodium'),  # Convert g to mg if needed
    }

def is_valid_product(product):
    """Check if product has enough data to be useful."""
    if not product.get('product_name'):
        return False

    nutriments = product.get('nutriments', {})

    # Must have at least energy and one other nutrient
    has_energy = nutriments.get('energy-kcal_100g') or nutriments.get('energy_100g')
    has_other = any([
        nutriments.get('proteins_100g'),
        nutriments.get('sugars_100g'),
        nutriments.get('sodium_100g'),
        nutriments.get('fat_100g')
    ])

    return has_energy or has_other

def process_product(off_product, existing_slugs):
    """Convert Open Food Facts product to Mizan format."""
    name = off_product.get('product_name', '').strip()
    brand = off_product.get('brands', '').split(',')[0].strip() if off_product.get('brands') else 'Unknown'

    # Clean up name
    if brand and name.lower().startswith(brand.lower()):
        name = name[len(brand):].strip(' -')

    full_name = f"{brand} {name}".strip()

    # Generate unique slug
    base_slug = slugify(full_name)
    slug = base_slug
    counter = 1
    while slug in existing_slugs:
        slug = f"{base_slug}-{counter}"
        counter += 1
    existing_slugs.add(slug)

    # Extract data
    nutrients = extract_nutrients(off_product.get('nutriments', {}))
    category = get_category(off_product)
    package_size = parse_quantity(off_product.get('quantity'))

    # Parse ingredients
    ingredients_text = off_product.get('ingredients_text', '')
    ingredients = [i.strip() for i in ingredients_text.split(',')[:15]] if ingredients_text else []

    # Identify flags/concerns
    flags = []
    if nutrients['sodium_mg'] > 500:
        flags.append("High Sodium")
    if nutrients['sugar_g'] > 15:
        flags.append("High Sugar")
    if nutrients['saturated_fat_g'] > 5:
        flags.append("High Saturated Fat")

    return {
        "id": off_product.get('code', slug),
        "slug": slug,
        "name": full_name,
        "brand": brand,
        "category": category.replace('-', ' ').title(),
        "category_slug": category,
        "package_size_g": package_size,
        "nutrients": nutrients,
        "ingredients": ingredients,
        "flags": flags,
        "image_url": off_product.get('image_url', ''),
        "source": "Open Food Facts",
        "source_url": f"https://world.openfoodfacts.org/product/{off_product.get('code', '')}"
    }

def fetch_indian_products(limit=100):
    """Fetch Indian packaged food products."""
    products = []
    existing_slugs = set()
    seen_codes = set()

    print(f"Fetching up to {limit} Indian products...")

    for brand in INDIAN_BRANDS:
        if len(products) >= limit:
            break

        print(f"  Searching: {brand}...")
        results = search_products(brand, page_size=30)

        for off_product in results:
            if len(products) >= limit:
                break

            code = off_product.get('code')
            if code in seen_codes:
                continue
            seen_codes.add(code)

            if not is_valid_product(off_product):
                continue

            try:
                product = process_product(off_product, existing_slugs)
                products.append(product)
                print(f"    Added: {product['name']}")
            except Exception as e:
                print(f"    Error processing product: {e}")

        time.sleep(0.5)  # Rate limiting

    return products

def main():
    parser = argparse.ArgumentParser(description="Fetch Indian products from Open Food Facts")
    parser.add_argument('--limit', type=int, default=100, help='Maximum products to fetch')
    parser.add_argument('--output', type=str, default=None, help='Output file path')
    args = parser.parse_args()

    # Fetch products
    products = fetch_indian_products(args.limit)

    print(f"\nFetched {len(products)} products")

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        script_dir = Path(__file__).parent
        output_path = script_dir.parent / "src" / "data" / "products_raw.json"

    # Save raw products
    data = {
        "source": "Open Food Facts",
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(products),
        "products": products
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Saved to: {output_path}")
    print("\nNext steps:")
    print("  1. Run: python scripts/calculate-scores.py src/data/products_raw.json src/data/products.json")
    print("  2. Review and verify the data")
    print("  3. Run: npm run build")

if __name__ == "__main__":
    main()
