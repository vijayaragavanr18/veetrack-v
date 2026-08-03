import puppeteer from 'puppeteer';

(async () => {
  console.log('Starting puppeteer...');
  const browser = await puppeteer.launch({ headless: 'new' });
  const page = await browser.newPage();
  
  // Set viewport to simulate a mobile phone
  await page.setViewport({ width: 390, height: 844 });
  
  console.log('Navigating to app...');
  await page.goto('http://localhost:3000/feed?q=NVIDIA', { waitUntil: 'networkidle0' });
  
  console.log('Evaluating DOM...');
  const metrics = await page.evaluate(() => {
    const layout = document.querySelector('main');
    const viewport = document.querySelector('[data-testid="story-viewport"]');
    
    // We need to find the image and the engagement row
    const images = Array.from(document.querySelectorAll('img'));
    const heroImage = images.find(img => img.src.includes('article') || img.closest('.aspect-\\[4\\/3\\]') || img.closest('.h-\\[50\\%\\]'));
    const heroContainer = heroImage ? heroImage.parentElement : null;
    
    // The engagement row is identified by having Heart, Bookmark, etc.
    const buttons = Array.from(document.querySelectorAll('button'));
    const heartBtn = buttons.find(b => b.innerHTML.includes('Heart') || b.querySelector('svg'));
    const engagementRow = heartBtn ? heartBtn.closest('.shrink-0.border-t') : null;
    
    return {
      main: layout ? layout.getBoundingClientRect() : null,
      viewport: viewport ? viewport.getBoundingClientRect() : null,
      heroContainer: heroContainer ? heroContainer.getBoundingClientRect() : null,
      engagementRow: engagementRow ? engagementRow.getBoundingClientRect() : null,
      viewportHeight: window.innerHeight,
    };
  });
  
  console.log(JSON.stringify(metrics, null, 2));
  
  await browser.close();
})();
