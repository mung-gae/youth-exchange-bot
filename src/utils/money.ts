export function assertPositiveInt(value:number, label='금액'){ if(!Number.isInteger(value)||value<1) throw new Error(`${label}은 1 이상의 정수여야 합니다.`); }
export function assertNonNegativeInt(value:number,label='금액'){ if(!Number.isInteger(value)||value<0) throw new Error(`${label}은 0 이상의 정수여야 합니다.`); }
export function formatWon(v:number){ return `${v.toLocaleString('ko-KR')}원`; }
export function saleUnitPrice(buyout:number,totalQty:number){ if(totalQty<=0) return 0; return Math.floor(Math.floor(buyout/totalQty)/1000)*1000; }
