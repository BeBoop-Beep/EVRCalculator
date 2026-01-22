print(f"Reverse EV Total: ${ev_reverse_total:.4f}")
        
        # Calculate EV totals by rarity
        ev_totals = self.calculator.calculate_rarity_ev_totals(df, ev_reverse_total)
        print("EV Totals by Rarity:", ev_totals)