const {defineConfig}=require('@playwright/test');
const path=require('node:path');
if(!process.env.ROOTLINE_UI_OUTPUT)throw new Error('Set ROOTLINE_UI_OUTPUT to the assigned browser evidence directory.');
module.exports=defineConfig({
 testDir:__dirname,testMatch:'rootline_owner_controls_browser.spec.js',workers:1,timeout:45000,
 outputDir:process.env.ROOTLINE_UI_OUTPUT,reporter:[['list']],
 use:{viewport:{width:1440,height:1000},headless:true,launchOptions:process.env.ROOTLINE_UI_BROWSER?{executablePath:process.env.ROOTLINE_UI_BROWSER}:{},trace:'retain-on-failure'},
 ...(process.env.ROOTLINE_UI_SERVER_COMMAND?{webServer:{cwd:path.resolve(__dirname,'..'),command:process.env.ROOTLINE_UI_SERVER_COMMAND,url:process.env.ROOTLINE_UI_BASE_URL+'/__irrigation_dialogue_ready',reuseExistingServer:false,timeout:120000}}:{})
});
