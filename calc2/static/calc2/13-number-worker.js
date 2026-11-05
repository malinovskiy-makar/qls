// Та же реализация и те же допуски, что у основного потока. URL содержит
// отпечаток 12-numbers.js из шаблона: кэш не смешивает версии форматтера.
const numbersURL=new URL(new URL(self.location.href).searchParams.get('numbers'));
// ManifestStaticFilesStorage добавляет хеш к имени при collectstatic.
if(numbersURL.origin!==self.location.origin || !/\/12-numbers(?:\.[a-f0-9]{12})?\.js$/.test(numbersURL.pathname))throw new Error('Неверный адрес форматтера');
importScripts(numbersURL.href);
self.onmessage = ({data}) => {
  try {
    self.postMessage({id:data.id, records:data.values.map(v => CalcNumber.classify(v))});
  } catch (error) {
    self.postMessage({id:data.id, error:String(error)});
  }
};
