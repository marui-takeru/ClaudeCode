const vm=require("vm"),fs=require("fs");// 区間ごとの平日の本数を「全国鉄道運行本数データ」と比べる:  node tools/check_honsu.js
const path=require('path');const root=path.join(__dirname,'..')+'/';
const c={window:{}};vm.createContext(c);vm.runInContext(fs.readFileSync(root+"data/network.js","utf8"),c);vm.runInContext(fs.readFileSync(root+"js/sim.js","utf8"),c);
const s=new c.window.Sim.Simulator(c.window.NETWORK);s.setDayType('weekday');
const alias={'ＪＲ松山駅前':'JR松山駅前','松山市':'松山市','松山市駅':'松山市','オレンジタウン':'オレンジタウン'};
const rows=fs.readFileSync(process.argv[2]||path.join(__dirname,'src/unkohonsu2026_shikoku.tsv'),'utf8').trim().split('\n').slice(process.argv[2]?0:1).map(l=>l.split('\t'));
const norm=n=>n==='松山市駅'?'松山市':n;
for(const [id,op,line,a0,b0,km,f,r] of rows){
  const a=norm(alias[a0]||a0), b=norm(alias[b0]||b0);
  let F=0,R=0; const who={};
  for(const p of s.patterns){ if(p.service.kind==='ship'||p.service.kind==='plane'||p.service.group==='jr_ltd'||p.service.id==='botchan')continue;
    const names=p.path.map(x=>norm(x[0]));
    const ia=names.indexOf(a), ib=names.indexOf(b); if(ia<0||ib<0)continue;
    const n=p.departures.length; if(ia<ib)F+=n;else R+=n; who[p.service.id]=(who[p.service.id]||0)+n; }
  console.log([op,line,a0+'-'+b0,'real',f,r,'model',F,R,JSON.stringify(who)].join(' '));
}
