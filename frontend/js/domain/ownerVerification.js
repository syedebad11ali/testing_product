  const CSV_FILES = [
    'assets/Dataset/apartments.csv',
    'assets/Dataset/commercials.csv',
    'assets/Dataset/houses.csv',
    'assets/Dataset/plots.csv',
    'assets/Dataset/portions.csv'
  ];
  const CONFIDENCE = {1:'High',2:'Medium',3:'Low',4:'Very low'};

  function parseCsv(text){
    const source = String(text || '').replace(/^\uFEFF/, '');
    const rows = [];
    let row = [], field = '', quoted = false;
    const finishRow = () => {
      row.push(field);
      rows.push(row);
      row = [];
      field = '';
    };

    for(let i=0;i<source.length;i++){
      const char = source[i];
      if(quoted){
        if(char==='"' && source[i+1]==='"'){
          field += '"';
          i++;
        } else if(char==='"'){
          quoted = false;
        } else {
          field += char;
        }
      } else if(char==='"' && field===''){
        quoted = true;
      } else if(char===','){
        row.push(field);
        field = '';
      } else if(char==='\n' || char==='\r'){
        if(char==='\r' && source[i+1]==='\n') i++;
        finishRow();
      } else {
        field += char;
      }
    }
    if(quoted) throw new Error('CSV contains an unterminated quoted field.');
    if(field!=='' || row.length) finishRow();
    if(!rows.length) return [];

    const headers = rows.shift().map(value=>value.trim());
    return rows.filter(values=>values.some(value=>value.trim()!==''))
      .map(values=>Object.fromEntries(headers.map((header,index)=>[header,(values[index] || '').trim()])));
  }

  function numberOrNull(value){
    if(value==null || String(value).trim()==='') return null;
    const parsed = Number(String(value).replace(/[^0-9.\-]/g,''));
    return Number.isFinite(parsed) ? parsed : null;
  }

  function parseFiles(files){
    const records = [];
    const sourceCounts = {};
    files.forEach(file=>{
      const rows = parseCsv(file.text);
      const sourceName = file.name.split(/[\\/]/).pop();
      sourceCounts[sourceName] = 0;
      rows.forEach(row=>{
        const propertyId = (row['Property ID'] || '').trim();
        if(!propertyId) return;
        records.push({
          ownerId:(row['Owner ID'] || '').trim(),
          ownerName:(row['Owner Name'] || row['Property Owner'] || '').trim(),
          listedOwner:(row['Property Owner'] || '').trim(),
          previousOwner:(row['Previous Owner'] || '').trim(),
          propertyId:propertyId,
          houseNumber:(row['House Number'] || '').trim(),
          streetNumber:(row['Street Number'] || '').trim(),
          area:(row['Area'] || '').trim(),
          block:numberOrNull(row['Block']),
          rooms:numberOrNull(row['Rooms']),
          propertyType:(row['Property Type'] || '').trim(),
          ownershipStatus:(row['Ownership Status'] || '').trim(),
          taxesStatus:(row['Taxes Status'] || '').trim(),
          legalCheck:(row['Legal Check'] || '').trim(),
          utilitiesBill:(row['Utilities Bill'] || '').trim(),
          price:numberOrNull(row['Price (PKR)']),
          sourceFile:sourceName
        });
        sourceCounts[sourceName]++;
      });
    });
    return {records:records,sourceCounts:sourceCounts};
  }

  function normalize(value){
    return String(value == null ? '' : value).trim().replace(/\s+/g,' ').toLowerCase();
  }

  function summarize(values){
    const avg = values.reduce((sum,value)=>sum+value,0)/values.length;
    if(values.length<2) return {mean:avg,std:null,count:values.length};
    const variance = values.reduce((sum,value)=>sum+Math.pow(value-avg,2),0)/(values.length-1);
    return {mean:avg,std:Math.sqrt(variance),count:values.length};
  }

  function aggregate(records,keyOf){
    const valuesByKey = new Map();
    records.forEach(record=>{
      const key = keyOf(record);
      if(!valuesByKey.has(key)) valuesByKey.set(key,[]);
      valuesByKey.get(key).push(record.price);
    });
    return new Map(Array.from(valuesByKey,([key,values])=>[key,summarize(values)]));
  }

  function roundThousand(value){ return Math.round(value/1000)*1000; }

  function createStore(parsed){
    const records = parsed.records;
    const byId = new Map(records.map(record=>[record.propertyId.toUpperCase(),record]));
    const priced = records.filter(record=>Number.isFinite(record.price) && record.price>0);
    const l1 = aggregate(priced,record=>JSON.stringify([normalize(record.area),record.block,normalize(record.propertyType)]));
    const l2 = aggregate(priced,record=>JSON.stringify([normalize(record.area),normalize(record.propertyType)]));
    const areaStats = aggregate(priced,record=>normalize(record.area));
    const typeStats = aggregate(priced,record=>normalize(record.propertyType));
    const globalStats = summarize(priced.map(record=>record.price));
    const ratios = new Map();

    l2.forEach((stats,key)=>{
      const [area,type] = JSON.parse(key);
      const typeMean = typeStats.get(type);
      if(!typeMean || !typeMean.mean) return;
      if(!ratios.has(area)) ratios.set(area,[]);
      ratios.get(area).push(stats.mean/typeMean.mean);
    });
    const areaFactor = new Map(Array.from(ratios,([area,values])=>[
      area,values.reduce((sum,value)=>sum+value,0)/values.length
    ]));

    function estimate(record){
      const area = normalize(record.area), type = normalize(record.propertyType);
      const block = record.block;
      const exact = l1.get(JSON.stringify([area,block,type]));
      if(exact && exact.count>=3)
        return {price:exact.mean,std:exact.std,level:1,label:'area + block + type mean',supportCount:exact.count};

      const areaType = l2.get(JSON.stringify([area,type]));
      if(areaType)
        return {price:areaType.mean,std:areaType.std,level:2,label:'area + type mean',supportCount:areaType.count};

      const areaMean = areaStats.get(area);
      if(areaFactor.has(area) && areaMean){
        const typeMean = typeStats.get(type);
        return typeMean
          ? {price:areaFactor.get(area)*typeMean.mean,std:null,level:3,label:'area factor x global type mean',supportCount:areaMean.count}
          : {price:areaMean.mean,std:null,level:3,label:'area mean (type has no priced records)',supportCount:areaMean.count};
      }

      const globalType = typeStats.get(type);
      return globalType
        ? {price:globalType.mean,std:globalType.std,level:4,label:'global type mean',supportCount:globalType.count}
        : {price:globalStats.mean,std:globalStats.std,level:4,label:'global mean (type has no priced records)',supportCount:globalStats.count};
    }

    function forecast(record,years,annualRate){
      const rate = annualRate == null ? 0.05 : Number(annualRate);
      if(!Number.isInteger(years) || years<0 || years>50)
        throw new RangeError('Forecast years must be a whole number from 0 to 50.');
      if(!Number.isFinite(rate) || rate<=-1)
        throw new RangeError('Annual appreciation rate must be finite and greater than -100%.');
      const estimateResult = estimate(record);
      const growth = Math.pow(1+rate,years);
      return {
        currentPrice:roundThousand(estimateResult.price),
        forecastPrice:roundThousand(estimateResult.price*growth),
        range:estimateResult.std==null ? null : {
          low:roundThousand(Math.max(estimateResult.price-estimateResult.std,0)*growth),
          high:roundThousand((estimateResult.price+estimateResult.std)*growth)
        },
        level:estimateResult.level,
        method:estimateResult.label,
        supportCount:estimateResult.supportCount,
        confidence:CONFIDENCE[estimateResult.level]
      };
    }

    return {
      records:records,
      recordCount:records.length,
      pricedCount:priced.length,
      sourceCounts:parsed.sourceCounts,
      lookup:propertyId=>byId.get(String(propertyId || '').trim().toUpperCase()) || null,
      estimate:estimate,
      forecast:forecast
    };
  }

  async function loadStore(fetcher){
    const request = fetcher || globalThis.fetch.bind(globalThis);
    const files = await Promise.all(CSV_FILES.map(async path=>{
      const response = await request(path);
      if(!response.ok) throw new Error('Could not load '+path+' (HTTP '+response.status+').');
      return {name:path,text:await response.text()};
    }));
    return createStore(parseFiles(files));
  }

  const api = {CSV_FILES:CSV_FILES,parseCsv:parseCsv,parseFiles:parseFiles,createStore:createStore,loadStore:loadStore};

export { CSV_FILES, parseCsv, parseFiles, createStore, loadStore };
export default api;
