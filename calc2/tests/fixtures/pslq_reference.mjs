// Unmodified relation() from c9b8d2b4, for differential and relative-cost tests.
// Do not update this reference to match an optimization under test.
export default function relation(x,accept){
  const norm=Math.hypot(...x),y=x.map(t=>t/norm),s=y.map((_,i)=>Math.hypot(...y.slice(i)));
  const H=y.map((_,i)=>[0,1].map(j=>i<j?0:i===j?s[i+1]/s[i]:-y[i]*y[j]/(s[j]*s[j+1])));
  const B=y.map((_,i)=>y.map((_,j)=>+(i===j)));
  const reduce=()=>{for(let i=1;i<3;i++)for(let j=i-1;j>=0;j--){
    if(Math.abs(H[j][j])<1e-25)return false;
    const t=Math.round(H[i][j]/H[j][j]);
    y[j]+=t*y[i];for(let k=0;k<=j;k++)H[i][k]-=t*H[j][k];
    for(let k=0;k<3;k++)B[k][j]+=t*B[k][i];
  }return B.every(row=>row.every(t=>Number.isSafeInteger(t)&&Math.abs(t)<=1e9));};
  for(let iter=0;iter<100;iter++){
    if(!reduce())return null;
    for(let j=0;j<3;j++){
      const co=B.map(row=>row[j]);
      const residual=Math.abs(co.reduce((sum,k,i)=>sum+k*x[i],0));
      if(residual>1e-9*Math.max(1,...co.map((k,i)=>Math.abs(k*x[i]))))continue;
      const r=accept(co);if(r)return r;
    }
    const m=1.2*Math.abs(H[1][1])>Math.abs(H[0][0])?1:0;
    [y[m],y[m+1]]=[y[m+1],y[m]];[H[m],H[m+1]]=[H[m+1],H[m]];
    for(let i=0;i<3;i++)[B[i][m],B[i][m+1]]=[B[i][m+1],B[i][m]];
    if(m===0){
      const n=Math.hypot(H[0][0],H[0][1]),a=H[0][0]/n,b=H[0][1]/n;
      for(let i=0;i<3;i++){const h=H[i][0];H[i][0]=a*h+b*H[i][1];H[i][1]=-b*h+a*H[i][1];}
    }
  }
  return null;
}
