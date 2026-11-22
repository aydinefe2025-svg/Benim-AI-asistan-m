// CANO-R1 digital assembly beta / original parametric geometry.
// Geometry in millimetres. Print-ready status is NOT implied.
// Export each part via openscad -o meshes/{part}.stl -D 'part="upper"' ...
// No bearings, servo models, clearances, wiring, fastening strength or torque verified.
$fn=48;
part = "assembly";
q_yaw=0;
q_shoulder=45;
q_elbow=-80;
q_wrist=35;
L1=120; L2=100; L3=50;
mount_bore=4.2; // assumed Ø4.2 mm through-holes; NOT a verified hardware selection

module bearing_boss(px,rad,depth) {
  translate([px,0,0]) rotate([90,0,0]) cylinder(h=depth,r=rad,center=true);
}
module beam(L, web_rad, boss_rad, depth, bore) {
  difference(){
    union(){
      hull(){bearing_boss(0,web_rad,depth);bearing_boss(L,web_rad,depth);}
      bearing_boss(0,boss_rad,depth);
      bearing_boss(L,boss_rad,depth);
    }
    bearing_boss(0,bore/2,depth+2);
    bearing_boss(L,bore/2,depth+2);
    // central web relief, preserves outer rails; nonconvex original STL
    if(L>70) hull(){
      bearing_boss(26,max(2,web_rad-4),depth+2);
      bearing_boss(L-26,max(2,web_rad-4),depth+2);
    }
  }
}
module base_pedestal(){
  difference(){
    union(){
      cylinder(r=32,h=8);
      translate([0,0,7]) cylinder(r=18,h=28);
      translate([0,0,34]) cylinder(r=17,h=2);
    }
    // Mounting holes through foot only; inspect print direction separately.
    for(x=[-22,22],y=[-22,22]) translate([x,y,-1]) cylinder(r=2.3,h=11);
    translate([0,0,12]) cylinder(r=11,h=24); // lightweight internal bore
  }
}
module yaw_rotor(){
  difference(){
    union(){
      translate([0,0,-36]) cylinder(r=9,h=38);
      translate([0,0,-3]) cylinder(r=14,h=7);
      translate([0,0,4]) cylinder(r=11,h=5);
    }
    translate([0,0,-37]) cylinder(r=3.1,h=47);
  }
}
module upper_arm(){ beam(L1,9,12,10,mount_bore); }
module forearm(){ beam(L2,8,11,10,mount_bore); }
module wrist_link(){ beam(L3,6,9,9,mount_bore); }
module gripper(){
  difference(){
    union(){
      translate([7,0,0]) cube([14,22,9],center=true);
      // Two fixed jaws with an open slot; no actuation mechanism is provided.
      for(y=[-11,11])translate([16,y,0]) cube([14,5,10],center=true);
    }
    translate([0,0,0]) rotate([90,0,0]) cylinder(r=mount_bore/2,h=30,center=true);
  }
}
// URDF world convention: positive pitch moves local +X upward, because axis is -Y.
module assembly(){
  color("#333840") base_pedestal();
  translate([0,0,70]) rotate([0,0,q_yaw]) {
    color("#666b70") yaw_rotor();
    rotate([0,-q_shoulder,0]) {
      translate([0,7,0]) color("#e99f3f") upper_arm();
      translate([L1,0,0])rotate([0,-q_elbow,0]){
        translate([0,-7,0]) color("#4d9bce") forearm();
        translate([L2,0,0]) rotate([0,-q_wrist,0]){
          translate([0,7,0]) color("#80b1a9") wrist_link();
          translate([L3,0,0]) color("#c65a5a") gripper();
        }
      }
    }
  }
}
if(part=="base") base_pedestal();
else if(part=="yaw") yaw_rotor();
else if(part=="upper") upper_arm();
else if(part=="forearm") forearm();
else if(part=="wrist") wrist_link();
else if(part=="gripper") gripper();
else assembly();