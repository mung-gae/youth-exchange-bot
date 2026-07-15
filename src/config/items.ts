import type { PriceTier, Season } from '../types.js';
export const FIXED_ITEMS:{name:string;season:Season;price:number;priceTier:PriceTier}[]=[
{name:'마스크',season:'봄',price:3000,priceTier:'저가'},{name:'화분',season:'봄',price:6000,priceTier:'중가'},{name:'원피스',season:'봄',price:10000,priceTier:'고가'},
{name:'선풍기',season:'여름',price:3000,priceTier:'저가'},{name:'튜브',season:'여름',price:6000,priceTier:'중가'},{name:'수영복',season:'여름',price:10000,priceTier:'고가'},
{name:'책',season:'가을',price:3000,priceTier:'저가'},{name:'머플러',season:'가을',price:6000,priceTier:'중가'},{name:'트렌치 코트',season:'가을',price:10000,priceTier:'고가'},
{name:'핫팩',season:'겨울',price:3000,priceTier:'저가'},{name:'목도리',season:'겨울',price:6000,priceTier:'중가'},{name:'패딩',season:'겨울',price:10000,priceTier:'고가'}];
export const SEASONS:Season[]=['봄','여름','가을','겨울']; export const PRICE_TIERS:PriceTier[]=['저가','중가','고가'];
