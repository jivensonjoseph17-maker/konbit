/*
 * Konbit — tèm (klè / nwa)
 * Chemen: frontend/theme.js
 *
 * Chaje nan <head> CHAK paj ki sèvi ak app.css, ANVAN app.css:
 *     <script src="theme.js"></script>
 * Li mete <html data-theme="dark"> anvan paj la parèt, pou yon moun ki
 * chwazi tèm nwa a pa wè paj la klere blan yon ti moman ("flash").
 *
 * Tèm klè a se pa defo. Chwa a sere sou aparèy la (localStorage).
 * Bouton pou chanje a nan ba anlè a (Konbit.theme nan api.js).
 */
(function () {
  try {
    if (localStorage.getItem('konbit.theme') === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
    }
  } catch (e) { /* navigasyon prive: tèm klè a */ }
})();