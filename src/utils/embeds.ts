export const brandTitle=(t:string)=>`청춘거래소 ${t}`;
export function textEmbed(title:string, description:string){ return {title:brandTitle(title), description, color:0x2ecc71}; }
