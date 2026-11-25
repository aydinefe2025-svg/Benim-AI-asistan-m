#pragma once
// Adapter for already computed F171 fields; only data conversion, no GR evolution changes.
#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <iostream>
struct ini_data {
 int ns,nu,nt; double r_e,Omega,F,D;
 std::vector<double> s,u,p,e,h;
 std::vector<std::array<double,17>> z;
};
static std::string j0740_file;
inline void RNS_params_set_default(){}
inline void RNS_params_set_inputfile(char* p){j0740_file=p;}
inline ini_data* RNS_make_initial_data(){
 auto* a=new ini_data;std::ifstream f(j0740_file);
 if(!(f>>a->ns>>a->nu>>a->nt>>a->r_e>>a->Omega>>a->F>>a->D)) throw std::runtime_error("J0740 header missing");
 if(a->ns<4||a->nu<4||a->nt<2||a->r_e<=0||a->F<=0||a->D<=0)throw std::runtime_error("J0740 invalid header");
 a->s.resize(a->ns);a->u.resize(a->nu);a->p.resize(a->nt);a->e.resize(a->nt);a->h.resize(a->nt);a->z.resize(a->ns*a->nu);
 for(auto& x:a->s)f>>x;for(auto& x:a->u)f>>x;
 for(int i=0;i<a->nt;i++)f>>a->p[i]>>a->e[i]>>a->h[i];
 for(auto& row:a->z)for(auto& x:row)f>>x;
 if(!f)throw std::runtime_error("J0740 truncated data");
 for(int i=1;i<a->nt;i++)if(!(a->p[i]>a->p[i-1]&&a->e[i]>a->e[i-1]&&a->h[i]>a->h[i-1]))throw std::runtime_error("J0740 EOS nonmonotone");
 return a;
}
inline void RNS_finalise(ini_data* a){delete a;}
namespace j0740 {
inline int loc(const std::vector<double>& a,double x){
 if(x<a.front()-1e-14||x>a.back()+1e-14)throw std::runtime_error("J0740 coordinates outside source");
 return std::clamp(int(std::upper_bound(a.begin(),a.end(),x)-a.begin())-1,0,int(a.size())-2);
}
inline double H(double a,double b,double da,double db,double t,double h){
 return (2*t*t*t-3*t*t+1)*a+(t*t*t-2*t*t+t)*h*da+(-2*t*t*t+3*t*t)*b+(t*t*t-t*t)*h*db;
}
inline double Hd(double a,double b,double da,double db,double t,double h){
 return ((6*t*t-6*t)*a+(-6*t*t+6*t)*b)/h+(3*t*t-4*t+1)*da+(3*t*t-2*t)*db;
}
struct Val{double f,ds,du;};
inline Val cubic(const ini_data& a,int i,int j,double t,double v,int k){
 double ds=a.s[i+1]-a.s[i],du=a.u[j+1]-a.u[j];
 double y[2],ys[2],yu[2],ysu[2];
 for(int b=0;b<2;b++){
 const auto& l=a.z[(i+b)*a.nu+j];const auto& r=a.z[(i+b)*a.nu+j+1];
 y[b]=H(l[k],r[k],l[k+2],r[k+2],v,du);
 ys[b]=H(l[k+1],r[k+1],l[k+3],r[k+3],v,du);
 yu[b]=Hd(l[k],r[k],l[k+2],r[k+2],v,du);
 ysu[b]=Hd(l[k+1],r[k+1],l[k+3],r[k+3],v,du);
 }
 return {H(y[0],y[1],ys[0],ys[1],t,ds),Hd(y[0],y[1],ys[0],ys[1],t,ds),H(yu[0],yu[1],ysu[0],ysu[1],t,ds)};
}
struct Point{
 double lapse,beta[3],g[3][3],K[3][3],rho,p,e,vel[3],W;
};
inline Point sample(const ini_data& a,double x,double y,double z){
 Point q{};double r=std::sqrt(x*x+y*y+z*z),R=std::hypot(x,y),s=r/(r+a.r_e),u=r>0?std::abs(z)/r:0;
 u=std::min(u,1.0);int i=loc(a.s,s),j=loc(a.u,u);
 double t=(s-a.s[i])/(a.s[i+1]-a.s[i]),v=(u-a.u[j])/(a.u[j+1]-a.u[j]);
 auto al=cubic(a,i,j,t,v,0),ga=cubic(a,i,j,t,v,4),ro=cubic(a,i,j,t,v,8),om=cubic(a,i,j,t,v,12);
 const auto& A=a.z[i*a.nu+j];const auto& B=a.z[(i+1)*a.nu+j];const auto& C=a.z[i*a.nu+j+1];const auto& D=a.z[(i+1)*a.nu+j+1];
 double p=(1-t)*(1-v)*A[16]+t*(1-v)*B[16]+(1-t)*v*C[16]+t*v*D[16];
 if(p<0)throw std::runtime_error("J0740 negative pressure");
 double e=0,h=0;
 if(p>0){
 if(p<a.p.front()){double f=std::pow(p/a.p.front(),.25);e=a.e.front()*f*f*f;h=4*std::log1p(a.p.front()/a.e.front()*f);}
 else{int l=loc(a.p,p);double m=(a.e[l+1]-a.e[l])/(a.p[l+1]-a.p[l]),dp=p-a.p[l];e=a.e[l]+m*dp;h=a.h[l]+std::log1p((1+m)*dp/(a.e[l]+a.p[l]))/(1+m);}
 }
 double ac=std::exp(2*al.f),bc=std::exp(ga.f-ro.f);
 q.lapse=std::exp((ga.f+ro.f)*.5);
 double phi[3]={-y,x,0},pos[3]={x,y,z},grad[3]={0,0,0},w=om.f/a.F;
 if(r>0)for(int d=0;d<3;d++)grad[d]=(om.ds*a.r_e/((r+a.r_e)*(r+a.r_e))*pos[d]/r+om.du*((d==2?(z>0?1.0:(z<0?-1.0:0.0))/r:0)-u*pos[d]/(r*r)))/a.F;
 double vsq=p>0?std::pow((a.Omega-w)*R*std::exp(-ro.f),2):0;
 if(!(vsq>=0&&vsq<1&&q.lapse>0&&ac>0&&bc>0))throw std::runtime_error("J0740 invalid metric or velocity");
 q.W=1/std::sqrt(1-vsq);q.rho=(e+p)*std::exp(-h)*a.D;q.p=p*a.D;q.e=e*a.D;
 for(int d=0;d<3;d++){
 q.beta[d]=-w*phi[d];q.vel[d]=p>0?q.W*(a.Omega-w)*phi[d]/q.lapse:0;
 for(int b=0;b<3;b++){
 q.g[d][b]=(d==b?ac:0)+(R>1e-14?(bc-ac)*phi[d]*phi[b]/(R*R):0);
 q.K[d][b]=-bc*(phi[d]*grad[b]+phi[b]*grad[d])/(2*q.lapse);
 }
 }
 return q;
}
}
inline void RNS_Cartesian_interpolation(ini_data* a,int* imin,int* imax,int* n,
 Real* x,Real* y,Real* z,Real* alp,Real* bx,Real* by,Real* bz,
 Real* gxx,Real* gxy,Real* gxz,Real* gyy,Real* gyz,Real* gzz,
 Real* Kxx,Real* Kxy,Real* Kxz,Real* Kyy,Real* Kyz,Real* Kzz,
 Real* rho,Real* eps,Real* vx,Real* vy,Real* vz,Real* ux,Real* uy,Real* uz,Real* pres){
 for(int k=imin[2];k<imax[2];k++)for(int j=imin[1];j<imax[1];j++)for(int i=imin[0];i<imax[0];i++){
 auto q=j0740::sample(*a,x[i],y[j],z[k]);int l=i+n[0]*(j+n[1]*k);
 auto put=[l](Real* p,double x){if(p)p[l]=x;};
 put(alp,q.lapse);put(bx,q.beta[0]);put(by,q.beta[1]);put(bz,q.beta[2]);
 put(gxx,q.g[0][0]);put(gxy,q.g[0][1]);put(gxz,q.g[0][2]);put(gyy,q.g[1][1]);put(gyz,q.g[1][2]);put(gzz,q.g[2][2]);
 put(Kxx,q.K[0][0]);put(Kxy,q.K[0][1]);put(Kxz,q.K[0][2]);put(Kyy,q.K[1][1]);put(Kyz,q.K[1][2]);put(Kzz,q.K[2][2]);
 put(rho,q.rho);put(pres,q.p);put(eps,q.rho>0?q.e/q.rho-1:0);
 put(ux,q.vel[0]);put(uy,q.vel[1]);put(uz,q.vel[2]);put(vx,q.vel[0]/q.W);put(vy,q.vel[1]/q.W);put(vz,q.vel[2]/q.W);
 }
}
