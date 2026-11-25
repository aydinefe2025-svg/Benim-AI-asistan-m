#include <cassert>
#include <iomanip>
using Real=double;
#include "j0740_rns.hpp"
int main(int argc,char**argv){
 if(argc!=5)return 2;
 RNS_params_set_inputfile(argv[1]);auto*a=RNS_make_initial_data();
 int N=std::stoi(argv[2]);double mb=std::stod(argv[3]),jj=std::stod(argv[4]),lim=2*a->r_e,dx=2*lim/N;
 double M=0,J=0,maxv=0,mindet=1e100,trace=0;long matter=0;
 for(int k=0;k<N;k++)for(int j=0;j<N;j++)for(int i=0;i<N;i++){
 double x=-lim+(i+.5)*dx,y=-lim+(j+.5)*dx,z=-lim+(k+.5)*dx;
 auto q=j0740::sample(*a,x,y,z);auto&g=q.g;
 double det=g[2][2]*(g[0][0]*g[1][1]-g[0][1]*g[1][0]);
 assert(std::isfinite(det)&&det>0&&q.lapse>0&&q.rho>=0&&q.p>=0);
 double W2=1;for(int u=0;u<3;u++)for(int v=0;v<3;v++)W2+=g[u][v]*q.vel[u]*q.vel[v];
 assert(std::abs(W2-q.W*q.W)<1e-12);
 double ud[3]={};for(int u=0;u<3;u++)for(int v=0;v<3;v++)ud[u]+=g[u][v]*q.vel[v];
 M+=std::sqrt(det)*q.rho*q.W*dx*dx*dx;
 J+=std::sqrt(det)*(q.e+q.p)*q.W*(x*ud[1]-y*ud[0])*dx*dx*dx;
 double tr=(g[1][1]*q.K[0][0]+g[0][0]*q.K[1][1]-2*g[0][1]*q.K[0][1])/(g[0][0]*g[1][1]-g[0][1]*g[1][0])+q.K[2][2]/g[2][2];
 trace=std::max(trace,std::abs(tr));maxv=std::max(maxv,std::sqrt(1-1/W2));mindet=std::min(mindet,det);matter+=q.rho>0;
 }
 // Exact axis/centre are sampled by the vertex-centred native evolution.
 for(double z:{0.0,a->r_e*.5,a->r_e*2}){auto q=j0740::sample(*a,0,0,z);assert(q.lapse>0&&std::isfinite(q.g[0][0])&&q.W==1);}
 std::cout<<std::setprecision(17)<<"J0740_IMPORT "<<N<<" "<<M<<" "<<J<<" "<<matter<<" "<<maxv<<" "<<mindet<<" "<<trace<<"\n";
 assert(std::abs(M/mb-1)<.002&&std::abs(J/jj-1)<.002&&trace<1e-12&&maxv<1&&matter>0);
 // Unit conversion negative control: native dimensionless rest density is not code density.
 assert(std::abs((M/a->D)/mb-1)>.1);
 RNS_finalise(a);
}
