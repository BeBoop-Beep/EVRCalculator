from ..helpers.card_helper import (clean_price_value, process_card, clean_condition,
    normalize_condition, parse_tcgplayer_printing, determine_special_type,
    build_external_variant_key)
from ..helpers.sealed_price_helper import parse_sealed_prices


class TCGPlayerParser:
    def __init__(self, pull_rate_mapping):
        """
        Initialize the parser with configuration
        
        Args:
            pull_rate_mapping: Dictionary mapping rarities to pull rates
        """
        self.pull_rate_mapping = pull_rate_mapping

    def parse_cards(self, raw_data):
        """
        Parse raw card data from TCGPlayer API
        
        Args:
            raw_data: Raw JSON response from TCGPlayer
            
        Returns:
            List of parsed and cleaned card dictionaries
        """
        raw_cards = raw_data.get("result", [])
        # Product ids identify commercial cards; canonical printings/finishes
        # beneath them are independently observable source variants.
        products = {}
        for row_index, card in enumerate(raw_cards):
            # Synthetic row identity is only a compatibility path for unit/
            # imported payloads; live TCGplayer rows always carry productID.
            product_id = str(card.get("productID") or f"_row:{row_index}").strip()
            products.setdefault(product_id, []).append(card)

        variant_groups = {}
        for product_id, rows in products.items():
            for row in rows:
                edition, printing_type = parse_tcgplayer_printing(row.get("printing"))
                special_type = determine_special_type(row.get("productName"), row.get("rarity"))
                signature = build_external_variant_key(edition, printing_type, special_type)
                variant_groups.setdefault((product_id, signature), []).append(row)

        selected_cards = []
        ambiguous_variant_groups = []
        missing_nm_variant_groups = []
        duplicate_nm_rows_deduped = 0
        for (product_id, signature), rows in variant_groups.items():
            near_mint = [
                row for row in rows
                if clean_condition(row.get("condition") or "") == "Near Mint"
            ]
            if not near_mint:
                missing_nm_variant_groups.append(f"{product_id}|{signature}")
                continue
            unique_nm = {}
            for row in near_mint:
                identity = tuple(sorted((key, repr(value)) for key, value in row.items()))
                unique_nm.setdefault(identity, row)
            duplicate_nm_rows_deduped += len(near_mint) - len(unique_nm)
            if len(unique_nm) != 1:
                ambiguous_variant_groups.append(f"{product_id}|{signature}")
                continue
            selected_cards.append(next(iter(unique_nm.values())))

        card_data = {}
        dropped_no_market = 0
        dropped_invalid = 0
        
        for card in selected_cards:
            
            product_name, card_dict = process_card(card, self.pull_rate_mapping)

            # Skip invalid cards
            if product_name is None:
                if not card.get('marketPrice'):
                    dropped_no_market += 1
                else:
                    dropped_invalid += 1
                continue
            
            # Create unique key to differentiate card variants
            # Include: product name, card number, rarity, special type, printing, and condition
            card_number = card_dict.get('number', '')
            rarity = card_dict.get('rarity', '')
            special_type = card_dict.get('specialType', '')
            printing = card_dict.get('printing', '')
            condition = card_dict.get('condition', '')
            
            # Build composite key - include card_number and rarity to distinguish different versions
            key_parts = [product_name, card_number, rarity]
            if special_type:
                key_parts.append(special_type)
            if printing:
                key_parts.append(printing)
            if condition:
                key_parts.append(condition)
            
            unique_key = "|".join(key_parts)

            # Store card data with unique key (keeps each variant separate)
            card_data[unique_key] = card_dict
            
        cards = list(card_data.values())
        
        print(
            f"[DIAG][parse_cards] raw={len(raw_cards)} products={len(products)} "
            f"kept={len(cards)} "
            f"dropped_no_market_price={dropped_no_market} "
            f"dropped_other={dropped_invalid} "
            f"source_variant_groups={len(variant_groups)} "
            f"rejected_ambiguous_variants={len(ambiguous_variant_groups)} "
            f"rejected_missing_nm_variants={len(missing_nm_variant_groups)}"
        )

        self.last_card_parse_report = {
            "raw_rows": len(raw_cards),
            "commercial_products": len(products),
            "source_variant_groups": len(variant_groups),
            "accepted_variant_groups": len(selected_cards),
            "payload_cards": len(cards),
            "ambiguous_variant_groups": sorted(ambiguous_variant_groups),
            "missing_nm_variant_groups": sorted(missing_nm_variant_groups),
            "rejected_ambiguous_variant_groups": len(ambiguous_variant_groups),
            "rejected_missing_nm_variant_groups": len(missing_nm_variant_groups),
            "duplicate_nm_rows_deduped": duplicate_nm_rows_deduped,
            "dropped_no_market_price": dropped_no_market,
        }

        return self._clean_card_data(cards)
    
    def parse_sealed_products(self, config, client):
        """
        Parse sealed product data from a single URL.

        Args:
            config: Configuration object containing SEALED_DETAILS_URL
            client: TCGPlayerClient instance

        Returns:
            List of cleaned sealed product dictionaries
        """
        set_name = config.SET_NAME

        # Fetch data from the URL
        sealed_raw = client.fetch_price_data(config.SEALED_DETAILS_URL)
        raw_products = sealed_raw.get("result", [])

        # Deduplicate strictly by productName
        product_map = {}

        for product in raw_products:
            product_name = product.get("productName")
            if not product_name:
                continue

            # Build sealed product dict WITHOUT their productID
            product_dict = {
                "name": product_name,
                "marketPrice": product.get("marketPrice"),
                "lowPrice": product.get("lowPrice"),
                "set": product.get("set"),
                "setAbbrv": product.get("setAbbrv"),
                "type": product.get("type"),
            }

            # Use productName as the unique key
            unique_key = product_name
            product_map[unique_key] = product_dict

        cleaned_products = list(product_map.values())

        # Use your existing cleaner
        return self._clean_sealed_data(cleaned_products, set_name)

    
    def _clean_card_data(self, cards):
        """Clean and validate card data before DTO conversion"""
        cleaned = []
        dropped_no_name = 0
        dropped_no_price = 0
        for card in cards:
            
            # Normalize condition to match database values
            condition = card.get('condition', '')
            condition = clean_condition(condition) if condition else 'Near Mint'
            normalized_condition = normalize_condition(condition)
            
            # Get raw rarity
            raw_rarity = card.get('rarity', '').strip()
            
            cleaned_card = {
                'name': card.get('productName', '').strip(),
                'card_number': card.get('number'),
                'rarity': raw_rarity,
                'variant': (card.get('specialType') or '').lower().strip(),  # Normalize to lowercase
                'condition': normalized_condition,  # Use normalized condition
                'printing': (card.get('printing') or '').strip(),
                'edition': (card.get('edition') or '').strip(),
                'printing_type': (card.get('printing_type') or '').strip(),
                'pull_rate': card.get('Pull Rate (1/X)'),
                'currency': 'USD',
                'source': 'TCGPlayer',
                'tcgplayer_product_id': card.get('tcgplayerProductID'),
                'external_catalog_key': card.get('externalCatalogKey'),
                'external_variant_key': card.get('externalVariantKey'),
                'external_source_reference': (f"https://www.tcgplayer.com/product/{card.get('tcgplayerProductID')}" if card.get('tcgplayerProductID') else None),
                'external_source_payload': card.get('externalSourcePayload') or {},
                'prices': {
                    'market': clean_price_value(card.get('Price ($)')),
                }
            }

            # Only include cards with valid data
            if cleaned_card['name'] and cleaned_card['prices']['market'] is not None:
                cleaned.append(cleaned_card)
            elif not cleaned_card['name']:
                dropped_no_name += 1
            else:
                dropped_no_price += 1
        
        print(
            f"[DIAG][_clean_card_data] after_clean={len(cleaned)} "
            f"dropped_no_name={dropped_no_name} "
            f"dropped_no_market_price={dropped_no_price}"
        )
        
        return cleaned
    
    def _clean_sealed_prices(self, prices, set_name):
        """Clean and validate sealed product prices and convert to list of dicts"""
        cleaned = []
        for product_type, price in prices.items():
            cleaned_price = clean_price_value(price)
            if cleaned_price is not None:
                cleaned.append({
                    'name': f"{set_name} {product_type}",  # e.g., "Prismatic Evolutions Booster Box"
                    'product_type': product_type,  # e.g., "Booster Box", "ETB"
                    'prices': {
                        'market': cleaned_price
                    }
                })
        return cleaned
    
    def _clean_sealed_data(self, products, set_name):
        """Clean and validate sealed product data"""
        cleaned = []
        for product in products:
            market_price = clean_price_value(product.get('marketPrice'))
            product_name = product.get('name', '').strip()
            
            if market_price is not None and product_name:
                cleaned.append({
                    'name': product_name,
                    'product_type': product.get('type', 'Sealed Product'),
                    'set_name': set_name,
                    'source': 'TCGPlayer',
                    'currency': 'USD',
                    'prices': {
                        'market': market_price,
                        'low': clean_price_value(product.get('lowPrice'))
                    }
                })
        return cleaned
