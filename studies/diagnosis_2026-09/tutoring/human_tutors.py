"""Hand-labeled human tutor searches from studies/human_ceiling/traces/*.json
(key_line entries; round = the trace's 'turn', which is the table round).
cat: win = a piece of the line that won or was the declared win attempt;
     engine = commander/engine piece feeding the line (Sisay, Cradle, Seedborn);
     ramp; interaction (removal/counter/protection/stax); value (draw engines etc.);
     unknown.  land=True for land tutors (Crop Rotation, Expedition Map).
off = cast outside the caster's own main phase (opponent's end step / in response).
won = the caster won this game.  winturn = the search happened in the winning round
of a game the caster won."""
import collections, json
H = [
 # pod, game, round, seat, tutor, fetched, cat, off, won, land, note
 ("2iA",1,2,"derevi","Worldly Tutor","Captain Sisay","engine",True,True,False,""),
 ("2iA",1,3,"rograkh_silas","Grim Tutor","?","unknown",False,False,False,""),
 ("2iA",1,3,"derevi","Captain Sisay","Gaea's Cradle","engine",False,True,False,"activated"),
 ("2iA",1,3,"godo","Urza's Saga","Manifold Key","value",False,False,True,"land-borne artifact tutor"),
 ("2iA",1,4,"godo","Goblin Engineer","Defense Grid","interaction",False,False,False,"to graveyard"),
 ("2iA",1,5,"rograkh_silas","Demonic Tutor","? (Necropotence likely)","value",False,False,False,""),
 ("2iA",1,5,"derevi","Chord of Calling","Nadu, Winged Wisdom","win",False,True,False,"win turn"),
 ("2iA",1,5,"derevi","Eldritch Evolution","Emiel the Blessed","win",False,True,False,"win turn"),
 ("2iA",1,5,"derevi","Finale of Devastation","Eternal Witness","win",False,True,False,"win turn, from graveyard"),
 ("5A6o",1,1,"cabbage_merchant","Green Sun's Zenith","Dryad Arbor","ramp",False,True,False,""),
 ("5A6o",1,3,"rog_ishai","Mystical Tutor","Swords to Plowshares","interaction",True,False,False,"in response"),
 ("5A6o",1,4,"cabbage_merchant","Urza's Saga","Sol Ring","ramp",False,True,True,"land-borne"),
 ("5A6o",1,4,"malcolm_kediss","Gamble","Curiosity","win",False,False,False,"win attempt; discarded by Gamble"),
 ("5A6o",1,5,"rog_ishai","Gifts Ungiven","Fierce Guardianship","interaction",True,False,False,"in response"),
 ("5A6o",1,5,"rog_ishai","Enlightened Tutor","Lion's Eye Diamond","win",True,False,False,"Breach line piece"),
 ("5A6o",1,6,"cabbage_merchant","Nature's Rhythm","Kuldotha Forgemaster","win",False,True,False,"win turn"),
 ("5A6o",1,6,"cabbage_merchant","Kuldotha Forgemaster","Nuka-Cola Vending Machine","win",False,True,False,"win turn, via Woodland copy"),
 ("B421",1,4,"yisan","Yisan, the Wanderer Bard","Birds of Paradise","ramp",True,False,False,""),
 ("B421",1,4,"yisan","Yisan, the Wanderer Bard","Collector Ouphe","interaction",False,False,False,"stax"),
 ("B421",1,6,"kinnan","Finale of Devastation","Volatile Stormdrake","interaction",False,False,False,"steal"),
 ("B421",1,7,"malcolm_vial","Demonic Tutor","Mystic Remora","value",False,False,False,""),
 ("B421",1,8,"kinnan","Yisan, the Wanderer Bard","Trophy Mage","value",False,False,False,"stolen Yisan"),
 ("B421",1,10,"sisay","Crop Rotation","Gaea's Cradle","win",True,True,True,"countered; lock-break line"),
 ("B421",1,10,"kinnan","Drift of Phantasms","?","unknown",False,False,False,"transmute"),
 ("Bq",1,3,"kinnan","Finale of Devastation","Seedborn Muse","win",False,True,False,"line enabler, win next round"),
 ("Bq",1,3,"cabbage_merchant","Worldly Tutor","Peregrin Took","engine",True,False,False,""),
 ("Bq",2,3,"yidris","Demonic Tutor","?","unknown",False,False,False,""),
 ("Bq",2,3,"rog_thrasios","Green Sun's Zenith","Seedborn Muse","engine",False,False,False,""),
 ("Bq",2,3,"kinnan","Worldly Tutor","Phyrexian Metamorph","engine",True,False,False,""),
 ("Bq",2,4,"cabbage_merchant","Transmutation Font","Clock of Omens","win",False,True,False,"win turn"),
 ("Bq",2,4,"cabbage_merchant","Transmutation Font","Academy Manufactor","win",False,True,False,"win turn"),
 ("Bq",3,3,"rog_thrasios","Chord of Calling","Oboro Breezecaller","win",False,True,False,""),
 ("Bq",3,3,"rog_thrasios","Nature's Rhythm","Seedborn Muse","engine",True,True,False,"in response"),
 ("Bq",3,4,"rog_thrasios","Expedition Map","Talon Gates of Madara","win",False,True,True,"win turn"),
 ("Bq",3,4,"rog_thrasios","Finale of Devastation","Six","win",False,True,False,"win turn, finisher X"),
 ("CxK",1,1,"bluefarm_sterling","Imperial Seal","Rhystic Study","value",False,False,False,""),
 ("CxK",1,5,"alan_tnt","Chord of Calling","Ranger-Captain of Eos","interaction",True,False,False,"in response"),
 ("OuY",2,2,"Rachel","Enlightened Tutor","Lotus Petal","ramp",False,False,False,"upkeep"),
 ("OuY",2,3,"Ian","Ranger-Captain of Eos","Signal Pest","value",False,False,False,"via Winota"),
 ("OuY",2,4,"Lua","Moggcatcher","Goblin Cratermaker","interaction",False,True,False,""),
 ("OuY",2,4,"Ian","Recruiter of the Guard","Solitude","interaction",False,False,False,""),
 ("OuY",2,5,"Lua","Moggcatcher","Kiki-Jiki, Mirror Breaker","win",False,True,False,"win turn"),
 ("n7Wp",1,1,"rog_ishai","Enlightened Tutor","Mystic Remora","value",False,False,False,""),
 ("n7Wp",1,3,"magda","Magda, Brazen Outlaw","Portal to Phyrexia","engine",False,True,False,"creator: objectively incorrect, GPG correct"),
 ("n7Wp",2,2,"selvala","Nature's Rhythm","Dryad Arbor","ramp",False,False,False,""),
 ("n7Wp",2,4,"magda","Magda, Brazen Outlaw","Portal to Phyrexia","engine",False,True,False,""),
 ("n7Wp",2,5,"selvala","Finale of Devastation","? 2-drop","unknown",False,False,False,""),
 ("n7Wp",2,6,"magda","Magda, Brazen Outlaw","?","win",False,True,False,"win turn"),
 ("sZA",1,2,"bluefarm_seat3","Vampiric Tutor","Mystic Remora/Rhystic Study","value",True,False,False,"graded as the losing decision"),
]
nonland = [h for h in H if not h[9]]
def pct(a,b): return f"{a}/{b} ({100*a/b:.0f}%)"
print("human tutor searches:", len(H), "nonland:", len(nonland))
r14 = sum(1 for h in nonland if h[2] <= 4)
print("rounds 1-4 (nonland):", pct(r14, len(nonland)))
print("median round:", sorted(h[2] for h in nonland)[len(nonland)//2])
cats = collections.Counter(h[6] for h in nonland)
print("categories:", dict(cats))
known = [h for h in nonland if h[6] != "unknown"]
winish = sum(1 for h in known if h[6] in ("win", "engine"))
print("win+engine share of known:", pct(winish, len(known)), " win-only:", pct(sum(1 for h in known if h[6]=='win'), len(known)))
print("off-turn:", pct(sum(1 for h in nonland if h[7]), len(nonland)))
# searches by the eventual winner
w = [h for h in nonland if h[8]]
print("searches by the game's winner:", len(w), "of which win/engine:", pct(sum(1 for h in w if h[6] in ('win','engine')), len(w)))
json.dump([dict(zip(["pod","game","round","seat","tutor","fetched","cat","off","won","land","note"], h)) for h in H],
          open(__file__.replace("human_tutors.py", "human_tutors.json"), "w"), indent=1)
