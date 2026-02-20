import { useState, useMemo } from "react";

const D = {"g":{"gameStage":200,"stageName":"Ending","day":1552,"hour":0,"charisma":40,"ralliedTroops":51,"spice":6144,"contactDistance":3,"fileSize":13697,"decompSize":22146},"st":[{"value":0,"name":"Start"},{"value":1,"name":"MetGurney"},{"value":4,"name":"FindProspectors"},{"value":8,"name":"ProspectorsFound"},{"value":12,"name":"FoundComms"},{"value":16,"name":"FoundHarvester"},{"value":20,"name":"PostHarvester"},{"value":24,"name":"EcologyIntro"},{"value":28,"name":"WaterDiscovery"},{"value":32,"name":"MidGame"},{"value":36,"name":"SietchTuek"},{"value":40,"name":"PreStilgar"},{"value":44,"name":"TakeStilgar"},{"value":48,"name":"PostStilgar"},{"value":53,"name":"LetoLeft"},{"value":56,"name":"HarkonnenPush"},{"value":60,"name":"Resistance"},{"value":64,"name":"CounterAttack"},{"value":72,"name":"PreWorm"},{"value":79,"name":"CanWormRide"},{"value":80,"name":"RodeWorm"},{"value":88,"name":"ArmyBuilding"},{"value":96,"name":"FindChani"},{"value":100,"name":"ChaniKidnapped"},{"value":104,"name":"ChaniReturned"},{"value":200,"name":"Ending"}],"tr":[{"i":0,"id":255,"j":1,"jn":"SpiceMining","si":84,"p":17155,"m":0,"ss":113,"as":49,"es":0,"eq":81,"el":["Knives","Atomics","Harvesters"],"mr":97,"d":0},{"i":1,"id":190,"j":1,"jn":"SpiceMining","si":188,"p":4866,"m":0,"ss":15,"as":70,"es":0,"eq":35,"el":["Knives","Krysknives","Bulbs"],"mr":149,"d":0},{"i":2,"id":208,"j":0,"jn":"Idle","si":176,"p":771,"m":0,"ss":97,"as":224,"es":255,"eq":94,"el":["Krysknives","LaserGuns","Weirding","Atomics","Harvesters"],"mr":100,"d":0},{"i":3,"id":40,"j":1,"jn":"SpiceMining","si":180,"p":259,"m":0,"ss":197,"as":197,"es":255,"eq":3,"el":["Knives","Krysknives"],"mr":93,"d":22},{"i":4,"id":243,"j":1,"jn":"SpiceMining","si":184,"p":23555,"m":0,"ss":226,"as":240,"es":255,"eq":86,"el":["Krysknives","LaserGuns","Atomics","Harvesters"],"mr":48,"d":26},{"i":5,"id":174,"j":2,"jn":"SpiceMining2","si":188,"p":3330,"m":0,"ss":15,"as":70,"es":0,"eq":36,"el":["LaserGuns","Bulbs"],"mr":5,"d":30},{"i":6,"id":150,"j":1,"jn":"SpiceMining","si":244,"p":36355,"m":0,"ss":247,"as":30,"es":0,"eq":86,"el":["Krysknives","LaserGuns","Atomics","Harvesters"],"mr":136,"d":20},{"i":7,"id":201,"j":0,"jn":"Idle","si":200,"p":3,"m":0,"ss":246,"as":253,"es":255,"eq":82,"el":["Krysknives","Atomics","Harvesters"],"mr":0,"d":24},{"i":8,"id":96,"j":1,"jn":"SpiceMining","si":140,"p":10498,"m":0,"ss":192,"as":71,"es":0,"eq":216,"el":["Weirding","Atomics","Harvesters","Ornis"],"mr":106,"d":26},{"i":9,"id":235,"j":1,"jn":"SpiceMining","si":224,"p":515,"m":0,"ss":22,"as":207,"es":255,"eq":81,"el":["Knives","Atomics","Harvesters"],"mr":0,"d":17},{"i":10,"id":252,"j":0,"jn":"Idle","si":100,"p":771,"m":0,"ss":33,"as":216,"es":255,"eq":88,"el":["Weirding","Atomics","Harvesters"],"mr":232,"d":8},{"i":11,"id":241,"j":0,"jn":"Idle","si":44,"p":3,"m":0,"ss":220,"as":13,"es":0,"eq":91,"el":["Knives","Krysknives","Weirding","Atomics","Harvesters"],"mr":0,"d":29},{"i":12,"id":75,"j":2,"jn":"SpiceMining2","si":204,"p":259,"m":0,"ss":92,"as":218,"es":255,"eq":59,"el":["Knives","Krysknives","Weirding","Atomics","Bulbs"],"mr":0,"d":22},{"i":13,"id":213,"j":1,"jn":"SpiceMining","si":64,"p":3,"m":0,"ss":177,"as":235,"es":255,"eq":46,"el":["Krysknives","LaserGuns","Weirding","Bulbs"],"mr":28,"d":22},{"i":14,"id":96,"j":1,"jn":"SpiceMining","si":88,"p":51971,"m":0,"ss":117,"as":5,"es":0,"eq":65,"el":["Knives","Harvesters"],"mr":33,"d":3},{"i":15,"id":235,"j":2,"jn":"SpiceMining2","si":224,"p":515,"m":0,"ss":22,"as":207,"es":255,"eq":81,"el":["Knives","Atomics","Harvesters"],"mr":0,"d":2},{"i":16,"id":94,"j":1,"jn":"SpiceMining","si":156,"p":3,"m":0,"ss":6,"as":235,"es":255,"eq":12,"el":["LaserGuns","Weirding"],"mr":0,"d":0},{"i":17,"id":107,"j":3,"jn":"MilTraining","si":224,"p":515,"m":0,"ss":22,"as":207,"es":255,"eq":81,"el":["Knives","Atomics","Harvesters"],"mr":0,"d":18},{"i":18,"id":190,"j":2,"jn":"SpiceMining2","si":100,"p":515,"m":0,"ss":7,"as":216,"es":255,"eq":96,"el":["Bulbs","Harvesters"],"mr":0,"d":3},{"i":19,"id":237,"j":1,"jn":"SpiceMining","si":104,"p":3,"m":0,"ss":44,"as":24,"es":0,"eq":91,"el":["Knives","Krysknives","Weirding","Atomics","Harvesters"],"mr":0,"d":25},{"i":20,"id":66,"j":3,"jn":"MilTraining","si":100,"p":771,"m":0,"ss":7,"as":216,"es":255,"eq":96,"el":["Bulbs","Harvesters"],"mr":0,"d":25},{"i":21,"id":172,"j":2,"jn":"SpiceMining2","si":136,"p":2,"m":0,"ss":17,"as":6,"es":0,"eq":235,"el":["Knives","Krysknives","Weirding","Bulbs","Harvesters","Ornis"],"mr":0,"d":6},{"i":22,"id":236,"j":1,"jn":"SpiceMining","si":80,"p":3,"m":0,"ss":38,"as":10,"es":0,"eq":96,"el":["Bulbs","Harvesters"],"mr":0,"d":31},{"i":23,"id":76,"j":1,"jn":"SpiceMining","si":164,"p":2,"m":0,"ss":51,"as":8,"es":0,"eq":89,"el":["Knives","Weirding","Atomics","Harvesters"],"mr":0,"d":23},{"i":24,"id":155,"j":1,"jn":"SpiceMining","si":136,"p":3,"m":0,"ss":17,"as":6,"es":0,"eq":70,"el":["Krysknives","LaserGuns","Harvesters"],"mr":0,"d":38},{"i":25,"id":222,"j":3,"jn":"MilTraining","si":204,"p":259,"m":0,"ss":92,"as":218,"es":255,"eq":59,"el":["Knives","Krysknives","Weirding","Atomics","Bulbs"],"mr":0,"d":13},{"i":26,"id":148,"j":1,"jn":"SpiceMining","si":100,"p":515,"m":0,"ss":7,"as":216,"es":255,"eq":96,"el":["Bulbs","Harvesters"],"mr":0,"d":6},{"i":27,"id":177,"j":10,"jn":"?10","si":188,"p":0,"m":0,"ss":49,"as":235,"es":255,"eq":0,"el":[],"mr":0,"d":23},{"i":29,"id":200,"j":9,"jn":"?9","si":84,"p":0,"m":0,"ss":62,"as":208,"es":255,"eq":0,"el":[],"mr":0,"d":5},{"i":30,"id":200,"j":10,"jn":"?10","si":84,"p":0,"m":0,"ss":62,"as":208,"es":255,"eq":0,"el":[],"mr":0,"d":2},{"i":31,"id":200,"j":11,"jn":"?11","si":84,"p":0,"m":0,"ss":62,"as":208,"es":255,"eq":0,"el":[],"mr":0,"d":30},{"i":32,"id":200,"j":9,"jn":"?9","si":168,"p":0,"m":0,"ss":38,"as":213,"es":255,"eq":0,"el":[],"mr":0,"d":24},{"i":33,"id":255,"j":10,"jn":"?10","si":168,"p":0,"m":0,"ss":38,"as":213,"es":255,"eq":0,"el":[],"mr":0,"d":28},{"i":34,"id":200,"j":11,"jn":"?11","si":168,"p":0,"m":0,"ss":38,"as":213,"es":255,"eq":0,"el":[],"mr":0,"d":15},{"i":35,"id":200,"j":0,"jn":"Idle","si":160,"p":3,"m":0,"ss":221,"as":27,"es":0,"eq":91,"el":["Knives","Krysknives","Weirding","Atomics","Harvesters"],"mr":0,"d":0},{"i":36,"id":162,"j":10,"jn":"?10","si":188,"p":0,"m":0,"ss":33,"as":237,"es":255,"eq":0,"el":[],"mr":0,"d":2},{"i":37,"id":0,"j":2,"jn":"SpiceMining2","si":240,"p":3,"m":0,"ss":246,"as":235,"es":255,"eq":82,"el":["Krysknives","Atomics","Harvesters"],"mr":0,"d":15},{"i":38,"id":212,"j":0,"jn":"Idle","si":172,"p":3,"m":0,"ss":199,"as":32,"es":0,"eq":81,"el":["Knives","Atomics","Harvesters"],"mr":0,"d":30},{"i":39,"id":191,"j":10,"jn":"?10","si":224,"p":3072,"m":5,"ss":22,"as":207,"es":255,"eq":0,"el":[],"mr":0,"d":29},{"i":41,"id":200,"j":10,"jn":"?10","si":56,"p":0,"m":0,"ss":42,"as":202,"es":255,"eq":0,"el":[],"mr":0,"d":3},{"i":42,"id":200,"j":11,"jn":"?11","si":56,"p":0,"m":0,"ss":42,"as":202,"es":255,"eq":0,"el":[],"mr":0,"d":27},{"i":43,"id":200,"j":5,"jn":"Ecology","si":100,"p":3,"m":0,"ss":7,"as":216,"es":255,"eq":96,"el":["Bulbs","Harvesters"],"mr":0,"d":27},{"i":44,"id":105,"j":10,"jn":"?10","si":188,"p":0,"m":0,"ss":7,"as":216,"es":255,"eq":0,"el":[],"mr":0,"d":19},{"i":46,"id":0,"j":3,"jn":"MilTraining","si":240,"p":3,"m":0,"ss":246,"as":235,"es":255,"eq":88,"el":["Weirding","Atomics","Harvesters"],"mr":0,"d":18},{"i":47,"id":192,"j":10,"jn":"?10","si":188,"p":0,"m":0,"ss":240,"as":221,"es":255,"eq":0,"el":[],"mr":0,"d":15},{"i":49,"id":0,"j":4,"jn":"Military","si":100,"p":771,"m":0,"ss":7,"as":216,"es":255,"eq":96,"el":["Bulbs","Harvesters"],"mr":0,"d":7},{"i":50,"id":145,"j":10,"jn":"?10","si":188,"p":17408,"m":5,"ss":249,"as":202,"es":255,"eq":0,"el":[],"mr":0,"d":22},{"i":52,"id":200,"j":9,"jn":"?9","si":112,"p":0,"m":0,"ss":39,"as":189,"es":255,"eq":0,"el":[],"mr":0,"d":9},{"i":53,"id":200,"j":9,"jn":"?9","si":68,"p":0,"m":0,"ss":12,"as":183,"es":255,"eq":0,"el":[],"mr":0,"d":13},{"i":54,"id":200,"j":4,"jn":"Military","si":224,"p":259,"m":0,"ss":22,"as":207,"es":255,"eq":81,"el":["Knives","Atomics","Harvesters"],"mr":0,"d":2},{"i":55,"id":211,"j":10,"jn":"?10","si":188,"p":0,"m":0,"ss":224,"as":193,"es":255,"eq":0,"el":[],"mr":0,"d":23},{"i":56,"id":0,"j":9,"jn":"?9","si":240,"p":31744,"m":5,"ss":246,"as":235,"es":255,"eq":0,"el":[],"mr":0,"d":0},{"i":57,"id":0,"j":1,"jn":"SpiceMining","si":108,"p":3,"m":0,"ss":33,"as":237,"es":255,"eq":54,"el":["Krysknives","LaserGuns","Atomics","Bulbs"],"mr":0,"d":31},{"i":58,"id":134,"j":0,"jn":"Idle","si":212,"p":24579,"m":5,"ss":232,"as":197,"es":255,"eq":97,"el":["Knives","Bulbs","Harvesters"],"mr":1,"d":16},{"i":59,"id":168,"j":6,"jn":"Equipment","si":240,"p":3,"m":0,"ss":246,"as":235,"es":255,"eq":8,"el":["Weirding"],"mr":0,"d":15},{"i":60,"id":158,"j":9,"jn":"?9","si":4,"p":0,"m":0,"ss":103,"as":195,"es":255,"eq":0,"el":[],"mr":0,"d":21},{"i":61,"id":200,"j":1,"jn":"SpiceMining","si":248,"p":3,"m":0,"ss":61,"as":239,"es":255,"eq":74,"el":["Krysknives","Weirding","Harvesters"],"mr":0,"d":22},{"i":62,"id":224,"j":1,"jn":"SpiceMining","si":148,"p":23555,"m":0,"ss":133,"as":246,"es":255,"eq":75,"el":["Knives","Krysknives","Weirding","Harvesters"],"mr":216,"d":16},{"i":63,"id":192,"j":10,"jn":"?10","si":188,"p":0,"m":0,"ss":92,"as":218,"es":255,"eq":0,"el":[],"mr":0,"d":30},{"i":65,"id":0,"j":0,"jn":"Idle","si":200,"p":3,"m":0,"ss":245,"as":246,"es":255,"eq":81,"el":["Knives","Atomics","Harvesters"],"mr":0,"d":20},{"i":66,"id":142,"j":9,"jn":"?9","si":28,"p":0,"m":0,"ss":58,"as":194,"es":255,"eq":0,"el":[],"mr":0,"d":20},{"i":67,"id":10,"j":0,"jn":"Idle","si":0,"p":0,"m":0,"ss":0,"as":0,"es":0,"eq":0,"el":[],"mr":0,"d":0}],"co":{"total":713,"chains":41,"empty":342,"ch":[{"s":1426,"e":1429,"sz":3,"n":1,"f":0,"l":0},{"s":1429,"e":1447,"sz":18,"n":1,"f":1,"l":1},{"s":1447,"e":1525,"sz":78,"n":5,"f":2,"l":6},{"s":1516,"e":1657,"sz":141,"n":11,"f":7,"l":20},{"s":1574,"e":1675,"sz":101,"n":5,"f":13,"l":22},{"s":1691,"e":1697,"sz":6,"n":1,"f":27,"l":27},{"s":1902,"e":1966,"sz":64,"n":3,"f":44,"l":48},{"s":2040,"e":2175,"sz":135,"n":5,"f":53,"l":57},{"s":1664,"e":2201,"sz":537,"n":36,"f":23,"l":67},{"s":2300,"e":2589,"sz":289,"n":14,"f":77,"l":95},{"s":2206,"e":2615,"sz":409,"n":17,"f":68,"l":98},{"s":2613,"e":2854,"sz":241,"n":1,"f":99,"l":99},{"s":3055,"e":3232,"sz":177,"n":8,"f":142,"l":154},{"s":3725,"e":3756,"sz":31,"n":1,"f":191,"l":191},{"s":2619,"e":3790,"sz":1171,"n":86,"f":100,"l":194},{"s":3782,"e":4048,"sz":266,"n":15,"f":195,"l":209},{"s":4022,"e":4177,"sz":155,"n":9,"f":210,"l":221},{"s":4091,"e":4902,"sz":811,"n":52,"f":214,"l":270},{"s":4871,"e":4928,"sz":57,"n":4,"f":271,"l":274},{"s":5025,"e":5037,"sz":12,"n":1,"f":280,"l":280},{"s":4943,"e":5067,"sz":124,"n":6,"f":275,"l":282},{"s":5119,"e":5443,"sz":324,"n":11,"f":286,"l":309},{"s":5453,"e":5493,"sz":40,"n":1,"f":310,"l":310},{"s":5606,"e":5780,"sz":174,"n":1,"f":322,"l":322},{"s":6197,"e":6222,"sz":25,"n":2,"f":368,"l":369},{"s":5040,"e":6431,"sz":1391,"n":87,"f":281,"l":384},{"s":6443,"e":6450,"sz":7,"n":1,"f":385,"l":385},{"s":6421,"e":6654,"sz":233,"n":11,"f":383,"l":397},{"s":6665,"e":6730,"sz":65,"n":5,"f":404,"l":408},{"s":7059,"e":7071,"sz":12,"n":1,"f":444,"l":444},{"s":6536,"e":7105,"sz":569,"n":47,"f":392,"l":448},{"s":7902,"e":7944,"sz":42,"n":3,"f":517,"l":520},{"s":8207,"e":8240,"sz":33,"n":1,"f":539,"l":539},{"s":8292,"e":8325,"sz":33,"n":1,"f":544,"l":544},{"s":7113,"e":8658,"sz":1545,"n":108,"f":449,"l":561},{"s":8606,"e":8908,"sz":302,"n":17,"f":562,"l":578},{"s":8876,"e":9442,"sz":566,"n":33,"f":579,"l":611},{"s":10073,"e":10092,"sz":19,"n":1,"f":644,"l":644},{"s":10199,"e":10240,"sz":41,"n":1,"f":651,"l":651},{"s":9450,"e":10836,"sz":1386,"n":87,"f":612,"l":700},{"s":10838,"e":10907,"sz":69,"n":12,"f":701,"l":712}],"en":[{"i":0,"o":1426,"s":3,"ov":false,"g":1429,"e":"byte[var_FC]"},{"i":1,"o":1429,"s":18,"ov":false,"g":1447,"e":"(byte[GameStage] == 0x01) ?16 (word[0x10] ?18 word[0x12] ?16 0x10 == 0x00)"},{"i":2,"o":1447,"s":78,"ov":true,"g":1525,"e":"(byte[GameStage] == 0x00) ?16 ((byte[0x25] <=s 0x00) ?16 ((word[0x84] + 0xAE26..."},{"i":27,"o":1691,"s":6,"ov":false,"g":1697,"e":"word[0x08] ?10 byte[var_FC]"},{"i":44,"o":1902,"s":64,"ov":true,"g":1966,"e":"(word[GameStage] ?29 word[0x83] ?10 0x8F2A ?10 byte[GameStage] == 0x0001) <u ..."},{"i":48,"o":1956,"s":10,"ov":false,"g":1966,"e":"(byte[var_FC] ?16 word[0x00]) ?16 (0xFCF7)"}]}};

const JC = {"SpiceMining":"#E8A838","SpiceMining2":"#D4943C","Idle":"#6B7280","MilTraining":"#DC2626","Military":"#991B1B","Ecology":"#16A34A","Equipment":"#7C3AED","Prospecting":"#CA8A04","Espionage":"#64748B"};
const hex = (v,w=2) => "0x"+v.toString(16).toUpperCase().padStart(w,"0");

function Bar({val,max=255,color="#E8A838",w="100%"}){
  const pct = Math.min(100, (val/max)*100);
  return <div style={{width:w,height:6,background:"#1a1510",borderRadius:3,overflow:"hidden"}}>
    <div style={{width:pct+"%",height:"100%",background:color,borderRadius:3,transition:"width 0.3s"}}/>
  </div>;
}

function Tag({children,color="#E8A838"}){
  return <span style={{display:"inline-block",padding:"1px 6px",fontSize:10,fontFamily:"monospace",background:color+"22",color,border:`1px solid ${color}44`,borderRadius:3,marginRight:3,marginBottom:2}}>{children}</span>;
}

function Panel({title,children,accent="#E8A838"}){
  return <div style={{background:"#0D0B08",border:"1px solid #2A2318",borderRadius:8,overflow:"hidden",marginBottom:12}}>
    <div style={{padding:"8px 14px",background:"#161210",borderBottom:"1px solid #2A2318",display:"flex",alignItems:"center",gap:8}}>
      <div style={{width:8,height:8,borderRadius:"50%",background:accent,boxShadow:`0 0 6px ${accent}66`}}/>
      <span style={{fontSize:11,fontWeight:700,letterSpacing:"0.08em",textTransform:"uppercase",color:"#A89070",fontFamily:'"JetBrains Mono",monospace'}}>{title}</span>
    </div>
    <div style={{padding:14}}>{children}</div>
  </div>;
}

function StatCard({label,value,sub,accent="#E8A838"}){
  return <div style={{background:"#161210",border:"1px solid #2A2318",borderRadius:6,padding:"10px 14px",minWidth:120,flex:1}}>
    <div style={{fontSize:10,color:"#6B5D4D",textTransform:"uppercase",letterSpacing:"0.1em",fontWeight:600,marginBottom:4,fontFamily:'"JetBrains Mono",monospace'}}>{label}</div>
    <div style={{fontSize:22,fontWeight:700,color:accent,fontFamily:'"JetBrains Mono",monospace'}}>{value}</div>
    {sub && <div style={{fontSize:10,color:"#6B5D4D",marginTop:2}}>{sub}</div>}
  </div>;
}

function GlobalsView(){
  const g = D.g;
  return <div>
    <div style={{display:"flex",gap:8,flexWrap:"wrap",marginBottom:12}}>
      <StatCard label="Game Stage" value={hex(g.gameStage)} sub={g.stageName} accent="#E8A838"/>
      <StatCard label="Day" value={g.day} sub={`Hour ${g.hour}`} accent="#7EC8E3"/>
      <StatCard label="Spice" value={`${(g.spice*10).toLocaleString()} kg`} sub={`Raw: ${g.spice}`} accent="#E8A838"/>
      <StatCard label="Charisma" value={g.charisma} sub={`Display: ${Math.floor(g.charisma/2)}`} accent="#C084FC"/>
    </div>
    <div style={{display:"flex",gap:8,flexWrap:"wrap",marginBottom:16}}>
      <StatCard label="Rallied Troops" value={g.ralliedTroops} accent="#F87171"/>
      <StatCard label="Contact Dist" value={g.contactDistance} accent="#6B7280"/>
      <StatCard label="File Size" value={`${g.fileSize.toLocaleString()}B`} sub={`→ ${g.decompSize.toLocaleString()}B decompressed`} accent="#6B5D4D"/>
    </div>
    <Panel title="Story Progression" accent="#E8A838">
      <div style={{display:"flex",flexWrap:"wrap",gap:4}}>
        {D.st.map(s => {
          const active = s.value <= g.gameStage;
          const current = s.value === g.gameStage;
          return <div key={s.value} style={{
            padding:"4px 8px",fontSize:10,fontFamily:"monospace",
            background:current?"#E8A83833":active?"#1E1A14":"#0D0B08",
            border:`1px solid ${current?"#E8A838":active?"#3D3020":"#1E1A14"}`,
            borderRadius:4,color:current?"#E8A838":active?"#A89070":"#3D3020",
            fontWeight:current?700:400,
          }}>
            {hex(s.value)} {s.name}
          </div>;
        })}
      </div>
    </Panel>
  </div>;
}

function TroopsView(){
  const [sel, setSel] = useState(null);
  const [filter, setFilter] = useState("all");
  const troops = useMemo(() => {
    if(filter==="all") return D.tr;
    return D.tr.filter(t => t.jn === filter || (filter==="active" && t.p > 0));
  }, [filter]);

  const jobs = [...new Set(D.tr.map(t=>t.jn))];
  const selT = sel !== null ? D.tr.find(t=>t.i===sel) : null;

  return <div>
    <div style={{display:"flex",gap:4,marginBottom:10,flexWrap:"wrap"}}>
      {["all","active",...jobs].map(f => <button key={f} onClick={()=>setFilter(f)} style={{
        padding:"3px 10px",fontSize:10,fontFamily:"monospace",cursor:"pointer",
        background:filter===f?"#E8A83833":"transparent",
        border:`1px solid ${filter===f?"#E8A838":"#2A2318"}`,
        color:filter===f?"#E8A838":"#6B5D4D",borderRadius:4,
      }}>{f}</button>)}
    </div>
    <div style={{display:"flex",gap:12}}>
      <div style={{flex:1,maxHeight:480,overflowY:"auto"}}>
        <table style={{width:"100%",borderCollapse:"collapse",fontSize:11,fontFamily:"monospace"}}>
          <thead><tr style={{borderBottom:"1px solid #2A2318"}}>
            {["#","Job","Pop","Equip"].map(h => <th key={h} style={{padding:"4px 6px",textAlign:"left",color:"#6B5D4D",fontSize:9,fontWeight:600,letterSpacing:"0.1em",textTransform:"uppercase"}}>{h}</th>)}
          </tr></thead>
          <tbody>{troops.map(t => <tr key={t.i} onClick={()=>setSel(t.i)} style={{
            cursor:"pointer",borderBottom:"1px solid #1E1A14",
            background:sel===t.i?"#E8A83811":"transparent",
          }}>
            <td style={{padding:"4px 6px",color:"#6B5D4D"}}>{t.i}</td>
            <td style={{padding:"4px 6px"}}><Tag color={JC[t.jn]||"#6B7280"}>{t.jn}</Tag></td>
            <td style={{padding:"4px 6px",color:t.p>0?"#E8A838":"#3D3020"}}>{t.p>0?t.p.toLocaleString():"-"}</td>
            <td style={{padding:"4px 6px"}}>{t.el.length>0?t.el.map(e=><Tag key={e} color="#7EC8E3">{e}</Tag>):<span style={{color:"#3D3020"}}>-</span>}</td>
          </tr>)}</tbody>
        </table>
      </div>
      {selT && <div style={{width:260,flexShrink:0}}>
        <Panel title={`Troop #${selT.i}`} accent={JC[selT.jn]||"#6B7280"}>
          <div style={{fontSize:11,fontFamily:"monospace",color:"#A89070"}}>
            <div style={{marginBottom:8}}>
              <span style={{color:"#6B5D4D"}}>ID:</span> {selT.id} &nbsp;
              <span style={{color:"#6B5D4D"}}>Sietch:</span> {selT.si}
            </div>
            <div style={{marginBottom:6}}>
              <span style={{color:"#6B5D4D"}}>Spice Skill</span>
              <div style={{display:"flex",alignItems:"center",gap:6}}><Bar val={selT.ss} color="#E8A838" w="100%"/><span>{selT.ss}</span></div>
            </div>
            <div style={{marginBottom:6}}>
              <span style={{color:"#6B5D4D"}}>Army Skill</span>
              <div style={{display:"flex",alignItems:"center",gap:6}}><Bar val={selT.as} color="#F87171" w="100%"/><span>{selT.as}</span></div>
            </div>
            <div style={{marginBottom:6}}>
              <span style={{color:"#6B5D4D"}}>Eco Skill</span>
              <div style={{display:"flex",alignItems:"center",gap:6}}><Bar val={selT.es} color="#16A34A" w="100%"/><span>{selT.es}</span></div>
            </div>
            <div style={{marginBottom:6}}>
              <span style={{color:"#6B5D4D"}}>Motivation</span>
              <div style={{display:"flex",alignItems:"center",gap:6}}><Bar val={selT.m} color="#C084FC" w="100%"/><span>{selT.m}</span></div>
            </div>
            <div style={{marginBottom:6}}>
              <span style={{color:"#6B5D4D"}}>Dissatisfaction</span>
              <div style={{display:"flex",alignItems:"center",gap:6}}><Bar val={selT.d} color="#F87171" w="100%"/><span>{selT.d}</span></div>
            </div>
            <div style={{marginTop:8,fontSize:10,color:"#6B5D4D"}}>
              Equipment: {hex(selT.eq)} Mining Rate: {selT.mr}
            </div>
          </div>
        </Panel>
      </div>}
    </div>
  </div>;
}

function SietchView(){
  const [filter,setFilter] = useState("all");
  const sietches = useMemo(() => {
    if(filter==="all") return D.si;
    if(filter==="discovered") return D.si.filter(s=>s.d);
    if(filter==="battle") return D.si.filter(s=>s.b);
    if(filter==="vegetation") return D.si.filter(s=>s.vg);
    return D.si;
  }, [filter]);

  return <div>
    <div style={{display:"flex",gap:4,marginBottom:10}}>
      {["all","discovered","battle","vegetation"].map(f => <button key={f} onClick={()=>setFilter(f)} style={{
        padding:"3px 10px",fontSize:10,fontFamily:"monospace",cursor:"pointer",
        background:filter===f?"#16A34A33":"transparent",
        border:`1px solid ${filter===f?"#16A34A":"#2A2318"}`,
        color:filter===f?"#16A34A":"#6B5D4D",borderRadius:4,
      }}>{f}</button>)}
    </div>
    <div style={{maxHeight:500,overflowY:"auto"}}>
      <table style={{width:"100%",borderCollapse:"collapse",fontSize:11,fontFamily:"monospace"}}>
        <thead><tr style={{borderBottom:"1px solid #2A2318"}}>
          {["#","Status","GPS","Rgn","Trp","SpDns","Equip","Wtr","Spc"].map(h => <th key={h} style={{padding:"4px 6px",textAlign:"left",color:"#6B5D4D",fontSize:9,fontWeight:600,letterSpacing:"0.1em",textTransform:"uppercase",position:"sticky",top:0,background:"#0D0B08"}}>{h}</th>)}
        </tr></thead>
        <tbody>{sietches.map(s => <tr key={s.i} style={{borderBottom:"1px solid #1E1A14"}}>
          <td style={{padding:"4px 6px",color:"#6B5D4D"}}>{s.i}</td>
          <td style={{padding:"4px 6px"}}>
            {s.d && <Tag color="#E8A838">D</Tag>}
            {s.v && <Tag color="#7EC8E3">V</Tag>}
            {s.vg && <Tag color="#16A34A">E</Tag>}
            {s.b && <Tag color="#F87171">B</Tag>}
            {!s.d&&!s.v&&!s.vg&&!s.b && <span style={{color:"#3D3020"}}>-</span>}
          </td>
          <td style={{padding:"4px 6px",color:"#6B5D4D",fontSize:10}}>({s.x},{s.y})</td>
          <td style={{padding:"4px 6px",color:s.r===0?"#16A34A":"#6B5D4D"}}>{s.r}</td>
          <td style={{padding:"4px 6px",color:"#A89070"}}>{s.t}</td>
          <td style={{padding:"4px 6px"}}><Bar val={s.sd} max={200} color="#E8A838" w={60}/></td>
          <td style={{padding:"4px 6px"}}>{s.el.length>0?s.el.map(e=><Tag key={e} color="#7EC8E3">{e}</Tag>):<span style={{color:"#3D3020"}}>-</span>}</td>
          <td style={{padding:"4px 6px",color:s.w>0?"#3B82F6":"#3D3020"}}>{s.w||"-"}</td>
          <td style={{padding:"4px 6px",color:s.sp>0?"#E8A838":"#3D3020"}}>{s.sp||"-"}</td>
        </tr>)}</tbody>
      </table>
    </div>
  </div>;
}

function ConditView(){
  const [view,setView] = useState("chains");
  const [selChain,setSelChain] = useState(null);

  return <div>
    <div style={{display:"flex",gap:8,marginBottom:12,flexWrap:"wrap"}}>
      <StatCard label="Total Entries" value={D.co.total} accent="#C084FC"/>
      <StatCard label="Chains" value={D.co.chains} accent="#7EC8E3"/>
      <StatCard label="Non-Empty" value={D.co.total-D.co.empty} accent="#E8A838"/>
      <StatCard label="Empty" value={D.co.empty} accent="#3D3020"/>
    </div>
    <div style={{display:"flex",gap:4,marginBottom:10}}>
      {["chains","entries"].map(v => <button key={v} onClick={()=>setView(v)} style={{
        padding:"3px 10px",fontSize:10,fontFamily:"monospace",cursor:"pointer",
        background:view===v?"#C084FC33":"transparent",
        border:`1px solid ${view===v?"#C084FC":"#2A2318"}`,
        color:view===v?"#C084FC":"#6B5D4D",borderRadius:4,
      }}>{v}</button>)}
    </div>
    {view==="chains" ? <div>
      <div style={{display:"flex",gap:12}}>
        <div style={{flex:1,maxHeight:400,overflowY:"auto"}}>
          {D.co.ch.map((c,ci) => <div key={ci} onClick={()=>setSelChain(ci)} style={{
            padding:"6px 10px",marginBottom:2,borderRadius:4,cursor:"pointer",fontSize:11,fontFamily:"monospace",
            background:selChain===ci?"#C084FC11":"transparent",
            border:`1px solid ${selChain===ci?"#C084FC44":"transparent"}`,
          }}>
            <div style={{display:"flex",justifyContent:"space-between"}}>
              <span style={{color:"#A89070"}}>Chain #{ci}</span>
              <span style={{color:"#6B5D4D"}}>{c.n} entries</span>
            </div>
            <div style={{display:"flex",justifyContent:"space-between",fontSize:10}}>
              <span style={{color:"#6B5D4D"}}>{hex(c.s,4)}–{hex(c.e,4)}</span>
              <span style={{color:c.sz>500?"#F87171":c.sz>100?"#E8A838":"#6B5D4D"}}>{c.sz}b</span>
            </div>
            <Bar val={c.sz} max={1600} color={c.sz>500?"#F87171":c.sz>100?"#E8A838":"#16A34A"} w="100%"/>
          </div>)}
        </div>
        {selChain !== null && <div style={{width:280,flexShrink:0}}>
          <Panel title={`Chain #${selChain}`} accent="#C084FC">
            <div style={{fontSize:11,fontFamily:"monospace",color:"#A89070"}}>
              <div><span style={{color:"#6B5D4D"}}>Range:</span> {hex(D.co.ch[selChain].s,4)} – {hex(D.co.ch[selChain].e,4)}</div>
              <div><span style={{color:"#6B5D4D"}}>Size:</span> {D.co.ch[selChain].sz} bytes</div>
              <div><span style={{color:"#6B5D4D"}}>Entries:</span> {D.co.ch[selChain].n} (#{D.co.ch[selChain].f}–#{D.co.ch[selChain].l})</div>
              <div style={{marginTop:8,fontSize:10,color:"#6B5D4D"}}>
                Multiple CONDIT indices share this bytecode chain. Earlier entries evaluate more conditions (longer path through shared bytecode).
              </div>
            </div>
          </Panel>
        </div>}
      </div>
    </div> : <div style={{maxHeight:450,overflowY:"auto"}}>
      {D.co.en.map(e => <div key={e.i} style={{padding:"6px 10px",marginBottom:2,borderRadius:4,borderLeft:`3px solid ${e.ov?"#E8A838":"#2A2318"}`,background:"#0D0B08"}}>
        <div style={{display:"flex",justifyContent:"space-between",marginBottom:2}}>
          <span style={{fontSize:11,fontFamily:"monospace",color:"#A89070"}}>Entry {e.i}</span>
          <span style={{fontSize:10,fontFamily:"monospace",color:"#6B5D4D"}}>{hex(e.o,4)} ({e.s}b){e.ov?" OVERFLOW":""}</span>
        </div>
        <div style={{fontSize:10,fontFamily:"monospace",color:"#7EC8E3",wordBreak:"break-all",lineHeight:1.4}}>{e.e}</div>
      </div>)}
      <div style={{padding:10,fontSize:10,color:"#6B5D4D",fontStyle:"italic"}}>Showing first 50 non-empty entries of 371. Use condit_decompiler.py for complete data.</div>
    </div>}
  </div>;
}

export default function DuneExplorer(){
  const [tab, setTab] = useState("globals");
  const tabs = [
    {id:"globals",label:"GLOBALS",icon:"◆"},
    {id:"troops",label:"TROOPS",icon:"⚔"},
    {id:"sietches",label:"SIETCHES",icon:"⌂"},
    {id:"condit",label:"CONDIT VM",icon:"⎔"},
  ];

  return <div style={{
    minHeight:"100vh",background:"#080604",color:"#D4C4A8",
    fontFamily:'"JetBrains Mono","SF Mono","Fira Code",monospace',
  }}>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap" rel="stylesheet"/>
    <div style={{maxWidth:960,margin:"0 auto",padding:"16px 20px"}}>
      <div style={{marginBottom:20,display:"flex",alignItems:"baseline",gap:12}}>
        <h1 style={{margin:0,fontSize:18,fontWeight:700,color:"#E8A838",letterSpacing:"0.12em"}}>DUNE</h1>
        <span style={{fontSize:11,color:"#6B5D4D",fontWeight:400}}>1992 Save Explorer — DUNE37S1.SAV</span>
      </div>
      <div style={{display:"flex",gap:2,marginBottom:16,borderBottom:"1px solid #2A2318",paddingBottom:0}}>
        {tabs.map(t => <button key={t.id} onClick={()=>setTab(t.id)} style={{
          padding:"8px 16px",fontSize:11,fontWeight:tab===t.id?600:400,
          cursor:"pointer",border:"none",borderBottom:tab===t.id?"2px solid #E8A838":"2px solid transparent",
          background:"transparent",color:tab===t.id?"#E8A838":"#6B5D4D",
          letterSpacing:"0.08em",fontFamily:"inherit",transition:"all 0.15s",
        }}>{t.icon} {t.label}</button>)}
      </div>
      {tab==="globals" && <GlobalsView/>}
      {tab==="troops" && <TroopsView/>}
      {tab==="sietches" && <SietchView/>}
      {tab==="condit" && <ConditView/>}
      <div style={{marginTop:20,padding:"10px 0",borderTop:"1px solid #1E1A14",fontSize:9,color:"#3D3020",textAlign:"center"}}>
        Decoded from DNCDPRG.EXE disassembly · Cryogenic/Spice86 C# source · DuneEdit2 · Manual RE
      </div>
    </div>
  </div>;
}
