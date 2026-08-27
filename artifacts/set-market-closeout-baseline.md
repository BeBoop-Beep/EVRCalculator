# Set Market closeout baseline (Phase 1)

Recorded before implementation edits on branch `feature/ui_updates_and_set_market` at `de785e46b26fd709b2eb225af1464f62c1bca4db`.

| Surface | Sealed fetch owner | Request count | Breadth source | Chase Concentration source | Error behavior | Retry behavior |
| --- | --- | ---: | --- | --- | --- | --- |
| Desktop Market Value Trend | `SetMarketOverviewSection` -> local `useSealedSetMarket(setId)` | 1 | Cards: `cardsMarket.marketBreadth`; Sealed: local `sealedState.payload.setMarket.marketBreadth`; Graded: none | Independent Standard Set Value (`standardValue`) plus Top 10 value; Cards only | Local hook changes to `error` and clears payload to `null`; transient and unavailable are not distinguished | No Sealed retry action |
| Desktop Top 10 | `TopChaseCardsPanel` -> second local `useSealedSetMarket(setId)` | 1 | N/A | N/A | Local hook changes to `error` and clears payload; generic ranking error | Cards retry is wired, but Sealed has no retry action |
| Mobile Market Snapshot | `SetMarketMobileSetValue` -> its own local `useSealedSetMarket(setId)` | 1 | Always `cardsMarket.marketBreadth`, even for Sealed; signals render only for Cards | `cardsTrend.currentValue` plus Top 10 value (incorrectly coupled to Cards Market Index trend) | Local hook changes to `error` and clears payload; Sealed may resolve/snap as unavailable | No Sealed retry action |
| Mobile Top 10 | `SetMarketMobileTopChase` -> independent `getPokemonSetSealedMarket(setId)` effect | 1 | N/A | N/A | Local effect changes to `error` and clears payload; generic ranking error | Cards retry is wired, but Sealed has no retry action |

Confirmed duplicate ownership: one desktop Market mount can issue two logical `/market/sealed` requests (Overview + Top 10), and one mobile Market mount can issue two (Market Snapshot + Top 10).
