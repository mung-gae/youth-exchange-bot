declare const process: any;
declare namespace NodeJS { type Timeout = any; }
declare module 'node:fs' { const x:any; export default x; }
declare module 'node:path' { const x:any; export default x; }
declare module 'better-sqlite3' { const Database:any; export default Database; }
declare module 'dotenv/config';
declare module 'dotenv' { export const config:any; }
declare module 'vitest';
declare module 'discord.js' {
 export const SlashCommandBuilder:any; export const ChannelType:any; export const ActionRowBuilder:any; export const ButtonBuilder:any; export const ButtonStyle:any; export const Client:any; export const GatewayIntentBits:any; export const Events:any; export const REST:any; export const Routes:any;
}
