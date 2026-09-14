(() => {
  'use strict';

  const features = window.TTRPG_FEATURES = window.TTRPG_FEATURES || {};
  features.registerLocalComponents = (Alpine) => {
    Alpine.data('infoPopover', () => ({ showInfo: false }));
    Alpine.data('storyHints', () => ({ showHints: false }));
  };
})();
