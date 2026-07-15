export type EventStatus='SETTING'|'BUYING'|'BUYING_CLOSED'|'BUYOUT_SETTING'|'BUYOUT_PUBLISHED'|'SEASON_SELECTED'|'SELLING'|'SELLING_CLOSED'|'SETTLED'|'ENDED';
export type Season='봄'|'여름'|'가을'|'겨울'; export type PriceTier='저가'|'중가'|'고가';
export type TxType='STARTING_FUND'|'ADMIN_FUND_GRANT'|'ITEM_PURCHASE'|'ITEM_SALE'|'ITEM_EXPIRATION';
export interface EventRow{event_id:number;guild_id:string;name:string;status:EventStatus;current_round:number;starting_fund:number;participant_role_id:string|null;selected_season:Season|null;sale_start_at:string|null;sale_end_at:string|null;created_at:string;ended_at:string|null;channel_id:string|null}
export interface ItemRow{item_id:number;name:string;season:Season;price:number;price_tier:PriceTier;is_public:number}
