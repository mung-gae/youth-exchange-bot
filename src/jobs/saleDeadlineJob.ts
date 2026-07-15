import { YouthExchangeService } from '../services/coreService.js';
export class SaleDeadlineJob{ private timers=new Map<number,NodeJS.Timeout>(); constructor(private svc:YouthExchangeService){}
schedule(eventId:number,endIso:string){ this.cancel(eventId); const delay=Math.max(0,new Date(endIso).getTime()-Date.now()); const t=setTimeout(()=>{ try{ this.svc.closeSelling(eventId); console.log(`[청춘거래소] 판매 자동 마감 완료 event=${eventId}`); }catch(e:any){ console.error('[청춘거래소] 판매 자동 마감 오류',{eventId,message:e.message}); } },delay); this.timers.set(eventId,t); }
cancel(eventId:number){ const t=this.timers.get(eventId); if(t) clearTimeout(t); this.timers.delete(eventId); }
restore(){ const rows=this.svc.db.prepare("SELECT event_id,sale_end_at FROM events WHERE status='SELLING' AND sale_end_at IS NOT NULL").all(); for(const r of rows){ if(new Date(r.sale_end_at)<=new Date()) this.svc.closeSelling(r.event_id); else this.schedule(r.event_id,r.sale_end_at); } console.log('[청춘거래소] 판매 마감 작업 복구 완료'); }
shutdown(){ for(const t of this.timers.values()) clearTimeout(t); this.timers.clear(); }}
