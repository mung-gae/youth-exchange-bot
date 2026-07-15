import { FIXED_ITEMS } from '../config/items.js';
export function seedItems(db:any){ const stmt=db.prepare('INSERT OR IGNORE INTO items(name,season,price,price_tier,is_public) VALUES(?,?,?,?,0)'); const tx=db.transaction(()=>{ for(const i of FIXED_ITEMS) stmt.run(i.name,i.season,i.price,i.priceTier); }); tx(); }
