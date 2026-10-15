"""Exercise the shipped JavaScript in Qt's JS engine, without a desktop."""

import json
from pathlib import Path
import unittest

from PySide6.QtCore import QCoreApplication
from PySide6.QtQml import QJSEngine


APP = QCoreApplication([])
ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "effect/contents/code/main.js").read_text()
SETUP = """
var ended, added, deleted;
var calls = [], warnings = [], serial = 0, factor = 1;
var Effect = {MapTexture:1, ShaderUniform:2, Size:3, Translation:4, Opacity:5,
              WindowForceBlurRole:6};
var QEasingCurve = {Linear:0};
var console = {warn:function(message){warnings.push(message)}, info:function(){}};
var effect = {
    addFragmentShader:function(){return 1},
    readConfig:function(key, fallback){return fallback},
    animationEnded:{connect:function(callback){ended=callback}}
};
var effects = {
    virtualScreenGeometry:{x:-1920,y:-1080,width:5760,height:3240},
    hasActiveFullScreenEffect:false, stackingOrder:[],
    windowAdded:{connect:function(callback){added=callback}},
    windowDeleted:{connect:function(callback){deleted=callback}}
};
function animate(options) {
    var ids = options.animations
        ? options.animations.map(function(){return ++serial}) : ++serial;
    calls.push({kind:"animate", ids:ids, options:options});
    return ids;
}
function cancel(ids){calls.push({kind:"cancel", ids:ids})}
function retarget(ids,value,duration){calls.push({kind:"retarget",ids:ids,value:value,duration:duration})}
function freezeInTime(ids,time){calls.push({kind:"freeze",ids:ids,time:time})}
function animationTime(duration){return duration * factor}
var w = {
    caption:"Synthetic test window", minimized:true, normalWindow:true,
    geometry:{x:300,y:160,width:700,height:440},
    expandedGeometry:{x:288,y:146,width:724,height:472},
    iconGeometry:{x:0,y:0,width:0,height:0},
    data:null, setData:function(role,value){this.data=value},
    minimizedChanged:{connect:function(callback){w.changed=callback}}
};
"""


class Targets(unittest.TestCase):
    def setUp(self):
        self.engine = QJSEngine()
        self.js(SETUP)
        self.js(SOURCE)

    def js(self, code):
        value = self.engine.evaluate(code)
        self.assertFalse(value.isError(), value.toString())
        return value.toVariant()

    def start(self, target):
        self.js("w.iconGeometry=" + json.dumps(target) + "; transition(w);")
        self.assertTrue(self.js("states.get(w).waiting"))
        self.js("ended(w, 0);")

    def test_all_panel_edges_and_other_outputs(self):
        targets = {
            "top": [900, 0, 48, 40],
            "bottom": [900, 2120, 48, 40],
            "left": [-1920, 200, 40, 48],
            "right": [3800, 200, 40, 48],
            "negative-output": [-1800, -1080, 48, 40],
            "other-output-bottom": [-1800, -40, 48, 40],
        }
        for label, dimensions in targets.items():
            with self.subTest(label=label):
                self.js("clear(w);")
                target = dict(zip(("x", "y", "width", "height"), dimensions))
                self.start(target)
                self.assertFalse(self.js("states.get(w).waiting"))
                self.assertEqual(self.js("states.get(w).target"), target)
                self.assertEqual(self.js("warnings.length"), 0)
                self.assertEqual(self.js("calls[calls.length-1].options.duration"), 300)
                self.assertTrue(self.js("""
                    var s=states.get(w), c=canvasFor(w.geometry,s.target);
                    c.x <= s.target.x+s.target.width/2 &&
                    c.x+c.width >= s.target.x+s.target.width/2 &&
                    c.y <= s.target.y+s.target.height/2 &&
                    c.y+c.height >= s.target.y+s.target.height/2;
                """))

    def test_invalid_native_geometry(self):
        for expression in (
            "undefined", "null", "{}", "{x:0,y:0,width:0,height:40}",
            "{x:0,y:0,width:-1,height:40}", "{x:NaN,y:0,width:40,height:40}",
            "{x:0,y:Infinity,width:40,height:40}",
            "{x:'0',y:0,width:40,height:40}",
            "{x:50000,y:0,width:40,height:40}",
            "{x:0,y:0,width:6000,height:40}",
        ):
            with self.subTest(expression=expression):
                self.assertFalse(self.js("usableTarget(" + expression + ")"))

    def test_bounded_wait_and_missing_target_cleanup(self):
        self.js("transition(w);")
        self.assertEqual(self.js("calls.filter(function(c){return c.kind==='animate'}).length"), 3)
        self.js("for(var i=0;i<24;i++) ended(w,0);")
        self.assertFalse(self.js("states.has(w)"))
        self.assertIsNone(self.js("w.data"))
        self.assertEqual(self.js("warnings.length"), 1)
        self.assertIn("no usable native task icon target", self.js("warnings[0]"))
        self.assertEqual(self.js("calls.filter(function(c){return c.kind==='cancel'}).length"), 0)
        self.assertEqual(self.js("""
            calls.filter(function(c){return c.kind==='animate' && c.options.duration===16}).length
        """), 24)
        self.assertEqual(self.js("""
            calls.filter(function(c){return c.kind==='retarget' && c.duration===1}).length
        """), self.js("Object.keys(uniformsFor(w,w.geometry,w.geometry,0)).length+1"))
        before = self.js("calls.length")
        self.js("ended(w,0);")
        self.assertEqual(self.js("calls.length"), before)

    def test_snapshot_precedes_layout_and_late_target(self):
        self.js("transition(w);")
        self.assertEqual(self.js("calls[0].options.animations[0].type"), 2)
        self.assertEqual(self.js("calls[1].options.animations[0].uniform"), "uProgress")
        self.assertEqual(self.js("calls[2].options.duration"), 16)
        self.js("for(var i=0;i<5;i++) ended(w,0);")
        self.js("w.iconGeometry={x:1000,y:2120,width:48,height:40}; ended(w,0);")
        self.assertFalse(self.js("states.get(w).waiting"))
        self.assertEqual(self.js("warnings.length"), 0)
        self.assertTrue(self.js("""
            var updates=calls.filter(function(c){return c.kind==='retarget' || c.kind==='freeze'});
            updates[0].duration===1 && updates[1].time===1 &&
            updates[2].duration===300 && updates[3].time===-1;
        """))

    def test_restore_reversal_and_normal_finish_do_not_cancel_zero(self):
        self.start({"x": 100, "y": 2120, "width": 48, "height": 40})
        seed = self.js("states.get(w).seed")
        self.js("w.minimized=false; transition(w);")
        self.assertEqual(self.js("states.get(w).seed"), seed)
        self.assertGreater(self.js("calls.filter(function(c){return c.kind==='cancel'}).length"), 0)
        self.js("ended(w,0);")
        self.assertFalse(self.js("states.get(w).waiting"))
        self.assertTrue(self.js("""
            calls.filter(function(c){return c.kind==='retarget'}).slice(-1)[0].value===0
        """))
        before = self.js("calls.filter(function(c){return c.kind==='cancel'}).length")
        self.js("ended(w,0);")
        self.assertFalse(self.js("states.has(w)"))
        self.assertIsNone(self.js("w.data"))
        self.assertEqual(self.js("calls.filter(function(c){return c.kind==='cancel'}).length"), before)

    def test_deleted_window_cancels_pending_capture(self):
        self.js("hook(w); transition(w); deleted(w);")
        self.assertFalse(self.js("states.has(w) || seeds.has(w) || hooked.has(w)"))
        self.assertIsNone(self.js("w.data"))
        self.assertEqual(self.js("calls.filter(function(c){return c.kind==='cancel'}).length"), 3)

    def test_global_animation_speed_and_disabled_animations(self):
        self.js("factor=0.8;")
        self.start({"x": 100, "y": 2120, "width": 48, "height": 40})
        self.assertEqual(self.js("calls[calls.length-1].options.duration"), 240)
        self.js("clear(w); factor=0; transition(w); ended(w,0);")
        self.assertFalse(self.js("states.has(w)"))
        self.assertIsNone(self.js("w.data"))
        self.assertEqual(self.js("warnings.length"), 0)

    def test_only_minimize_and_restore_hooks(self):
        self.js("added(w); added(w);")
        self.assertTrue(self.js("typeof w.changed==='function'"))
        self.assertEqual(self.js("hooked.size"), 1)
        self.assertEqual(self.js("calls.length"), 0)
        self.js("effects.hasActiveFullScreenEffect=true; w.changed();")
        self.assertFalse(self.js("states.has(w)"))
        self.assertEqual(self.js("calls.length"), 0)
        self.js("effects.hasActiveFullScreenEffect=false; w.normalWindow=false; w.changed();")
        self.assertFalse(self.js("states.has(w)"))


if __name__ == "__main__":
    unittest.main()
