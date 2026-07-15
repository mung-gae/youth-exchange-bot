import 'dotenv/config';
import { REST, Routes } from 'discord.js';
import { command } from './commands/seasonInvestment/command.js';
const missing = ['DISCORD_TOKEN', 'CLIENT_ID', 'GUILD_ID'].filter(k => !process.env[k]);
if (missing.length) {
    console.error(`[청춘거래소] 명령어 등록 필수 환경 변수가 누락되었습니다: ${missing.join(', ')}`);
    process.exit(1);
}
const rest = new REST({ version: '10' }).setToken(process.env.DISCORD_TOKEN);
await rest.put(Routes.applicationGuildCommands(process.env.CLIENT_ID, process.env.GUILD_ID), { body: [command.toJSON()] });
console.log('[청춘거래소] /계절투자 슬래시 명령어 등록 완료');
