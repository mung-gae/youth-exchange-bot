import 'dotenv/config';
import { Client, Events, GatewayIntentBits, REST, Routes } from 'discord.js';
import { command } from './commands/seasonInvestment/command.js';
import { handleSeasonInvestment } from './commands/seasonInvestment/handler.js';
import { openDatabase } from './database/connection.js';
import { migrate } from './database/schema.js';
import { seedItems } from './database/seed.js';
import { SaleDeadlineJob } from './jobs/saleDeadlineJob.js';
import { YouthExchangeService } from './services/coreService.js';
function requireEnv() {
    const miss = ['DISCORD_TOKEN', 'CLIENT_ID', 'GUILD_ID'].filter((key) => !process.env[key]);
    if (miss.length) {
        console.error(`[청춘거래소] 필수 환경 변수가 누락되었습니다: ${miss.join(', ')}`);
        process.exitCode = 1;
        return false;
    }
    return true;
}
async function registerGuildCommands() {
    const rest = new REST({ version: '10' }).setToken(process.env.DISCORD_TOKEN);
    await rest.put(Routes.applicationGuildCommands(process.env.CLIENT_ID, process.env.GUILD_ID), {
        body: [command.toJSON()],
    });
    console.log('[청춘거래소] /계절투자 슬래시 명령어 자동 등록 완료');
}
process.on('unhandledRejection', (error) => console.error('[청춘거래소] 처리되지 않은 Promise 오류', error));
process.on('uncaughtException', (error) => console.error('[청춘거래소] 처리되지 않은 오류', error));
const db = openDatabase();
migrate(db);
seedItems(db);
const svc = new YouthExchangeService(db);
const jobs = new SaleDeadlineJob(svc);
if (requireEnv()) {
    await registerGuildCommands();
    const client = new Client({ intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMembers] });
    client.once(Events.ClientReady, () => {
        console.log('[청춘거래소] Discord 로그인 완료');
        client.user?.setActivity('청춘거래소 /계절투자');
        jobs.restore();
        console.log('[청춘거래소] 준비 완료');
    });
    client.on(Events.InteractionCreate, async (interaction) => {
        if (interaction.isChatInputCommand?.() && interaction.commandName === '계절투자') {
            await handleSeasonInvestment(interaction, svc);
        }
    });
    const shutdown = () => {
        console.log('[청춘거래소] 종료 처리 중');
        jobs.shutdown();
        db.close();
        client.destroy();
        process.exit(0);
    };
    process.on('SIGINT', shutdown);
    process.on('SIGTERM', shutdown);
    await client.login(process.env.DISCORD_TOKEN);
}
else {
    db.close();
}
